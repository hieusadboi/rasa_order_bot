# actions.py - Rasa custom actions connecting to SQL Server (Windows Auth)
from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import pyodbc
import json
import re

# Update connection string if needed
CONN_STR = (
    "Driver={SQL Server};"
    "Server=HIEU;"
    "Database=QuanLyQuanAn;"
    "Trusted_Connection=yes;"
)

def db_connect():
    return pyodbc.connect(CONN_STR)

def search_foods(food_raw: str) -> List[Dict]:
    # naive search: split words and use LIKE on foodName
    words = [w.strip() for w in re.split(r"\s+", food_raw) if w.strip()]
    sql = "SELECT idFood, foodName, price FROM Food WHERE " + " AND ".join([f"foodName LIKE ?" for _ in words]) + " ORDER BY foodName"
    params = [f"%{w}%" for w in words]
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(idFood=row[0], foodName=row[1], price=float(row[2])) for row in rows]
    finally:
        cursor.close()
        conn.close()

def find_table_by_text(text: str) -> Optional[str]:
    t = text.lower().strip()
    if 'mang' in t:
        return 'Mang về'
    # detect 'bàn' + number
    m = re.search(r"bàn\s*(vip\s*)?(\d+)", t, flags=re.IGNORECASE)
    if m:
        prefix = 'Bàn Vip ' if m.group(1) else 'Bàn '
        return prefix + m.group(2)
    m2 = re.search(r"bàn\s*(\d+)", t, flags=re.IGNORECASE)
    if m2:
        return 'Bàn ' + m2.group(1)
    return None

class ActionProcessOrder(Action):
    def name(self) -> Text:
        return "action_process_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # gather latest user message
        text = tracker.latest_message.get('text', '') or ''
        # try extract table if present in same utterance
        table = find_table_by_text(text)
        if table:
            # set slot
            slot_events = [SlotSet('table_name', table)]
        else:
            slot_events = []

        # extract simple quantities and food mentions via regex: e.g. '2 phở', 'một phở'
        # number words basic mapping
        nummap = { 'một':1,'mot':1,'1':1,'hai':2,'2':2,'ba':3,'3':3,'bốn':4,'4':4,'năm':5,'5':5 }
        pattern = re.compile(r"(?:(\d+|một|mot|hai|ba|bốn|nam|năm)\s+([\w\sàáạảãâầấậẩẫăằắặẳẵêềếệểễôơưứừữựếé]+?))(?:,|và|va|\.|$)", flags=re.IGNORECASE)
        matches = pattern.findall(text)
        items = []
        for m in matches:
            qty_token = m[0].lower()
            qty = nummap.get(qty_token, None)
            if qty is None:
                try:
                    qty = int(qty_token)
                except:
                    qty = 1
            food_raw = m[1].strip()
            items.append({'food_raw': food_raw, 'quantity': qty})

        # fallback: if no regex matches, try to see if user said like '3 coca' shorter form
        if not items:
            short_pattern = re.compile(r"(\d+)\s+([\w\s]+)", flags=re.IGNORECASE)
            m = short_pattern.search(text)
            if m:
                items.append({'food_raw': m.group(2).strip(), 'quantity': int(m.group(1))})

        # if still empty, try get entity extractor output
        if not items:
            ents = tracker.latest_message.get('entities', [])
            for e in ents:
                if e.get('entity') == 'food':
                    items.append({'food_raw': e.get('value'), 'quantity': 1})
                if e.get('entity') == 'quantity':
                    # if quantity exists but no food, skip
                    pass

        # resolve each food against DB
        resolved = []
        pending_options = []
        for it in items:
            options = search_foods(it['food_raw'])
            if len(options) == 0:
                # unknown food, add as unknown
                resolved.append({'food': it['food_raw'], 'quantity': it['quantity'], 'idFood': None})
            elif len(options) == 1:
                opt = options[0]
                resolved.append({'food': opt['foodName'], 'quantity': it['quantity'], 'idFood': opt['idFood'], 'price': opt['price']})
            else:
                # multiple choices -> need user to pick, collect options and ask
                pending_options.append({'raw': it['food_raw'], 'quantity': it['quantity'], 'options': options})

        # if pending options exist -> ask user to choose from list
        if pending_options:
            # for simplicity, only handle first ambiguous item here
            po = pending_options[0]
            text_lines = [f"Có {len(po['options'])} món liên quan đến '{po['raw']}', bạn muốn món nào?\n"]
            for idx,opt in enumerate(po['options'], start=1):
                text_lines.append(f"{idx}. {opt['foodName']} - {opt['price']:,.0f}đ")
            text_lines.append("Vui lòng trả lời bằng số (ví dụ: 1) hoặc tên món.")
            dispatcher.utter_message('\n'.join(text_lines))
            # save partial resolved and pending in slot
            slot_value = {'resolved': resolved, 'pending': pending_options, 'table': tracker.get_slot('table_name')}
            return slot_events + [SlotSet('pending_order', json.dumps(slot_value))]

        # no ambiguous items -> create order summary and ask for confirmation
        order_summary_parts = []
        for r in resolved:
            order_summary_parts.append(f"{r['quantity']} {r['food']}")
        order_summary = ' và '.join(order_summary_parts) if order_summary_parts else 'không có món rõ ràng'

        table_confirm = tracker.get_slot('table_name') or table or 'Mang về'
        # if table not set, default to Mang về (per your choice B)
        if not table_confirm:
            table_confirm = 'Mang về'
            slot_events.append(SlotSet('table_name', table_confirm))

        payload = {
            'message': f"Dạ, bạn gọi {order_summary} tại {table_confirm}, đúng không ạ?",
            'order': resolved,
            'table': table_confirm,
            'status': 'pending_confirmation'
        }
        # utter with structured json so client can parse easily
        dispatcher.utter_message(text=payload['message'], json_message=payload)
        return slot_events + [SlotSet('pending_order', json.dumps({'resolved': resolved, 'pending': [], 'table': table_confirm}))]

class ActionConfirmOrder(Action):
    def name(self) -> Text:
        return "action_confirm_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # read pending_order slot and insert into DB
        p = tracker.get_slot('pending_order')
        if not p:
            dispatcher.utter_message(text="Không có đơn hàng đang chờ để lưu.")
            return []
        payload = json.loads(p)
        resolved = payload.get('resolved', [])
        table_name = payload.get('table') or tracker.get_slot('table_name') or 'Mang về'

        # find table id
        conn = db_connect()
        cur = conn.cursor()
        try:
            cur.execute("SELECT idTable FROM TableFood WHERE tableName = ?", (table_name,))
            row = cur.fetchone()
            if row:
                idTable = int(row[0])
            else:
                # fallback: if 'Mang về' not exist, create it or fail
                cur.execute("SELECT idTable FROM TableFood WHERE tableName = 'Mang về'")
                rr = cur.fetchone()
                if rr:
                    idTable = int(rr[0])
                else:
                    # create 'Mang về' table
                    cur.execute("INSERT INTO TableFood (tableName, status) VALUES (?, ?)", ('Mang về','Trống'))
                    conn.commit()
                    idTable = cur.execute("SELECT SCOPE_IDENTITY()").fetchval()
            # create Bill
            createdBy = 'system_voice'  # you can change to real user
            cur.execute("INSERT INTO Bill (DateCheckIn, idTable, status, createdBy) VALUES (GETDATE(), ?, 0, ?)", (idTable, createdBy))
            conn.commit()
            # get idBill
            # SCOPE_IDENTITY via SELECT CAST(SCOPE_IDENTITY() as int)
            cur.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
            idBill = int(cur.fetchone()[0])
            # insert each item
            for it in resolved:
                idFood = it.get('idFood')
                qty = it.get('quantity',1)
                if idFood:
                    cur.execute("INSERT INTO BillInfo (idBill, idFood, count) VALUES (?, ?, ?)", (idBill, idFood, qty))
            conn.commit()
        finally:
            cur.close()
            conn.close()

        dispatcher.utter_message(text="Đã lưu đơn vào hệ thống.")
        # clear pending_order slot
        return [SlotSet('pending_order', None), SlotSet('table_name', None)]

class ActionCancelOrder(Action):
    def name(self) -> Text:
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Đã hủy đơn hàng." )
        return [SlotSet('pending_order', None), SlotSet('table_name', None)]

class ActionListFoodOptions(Action):
    def name(self) -> Text:
        return "action_list_food_options"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        p = tracker.get_slot('pending_order')
        if not p:
            dispatcher.utter_message(text="Không có mục nào để chọn.")
            return []
        payload = json.loads(p)
        if payload.get('pending'):
            po = payload['pending'][0]
            lines = [f"Có {len(po['options'])} món liên quan đến '{po['raw']}':"]
            for idx,opt in enumerate(po['options'], start=1):
                lines.append(f"{idx}. {opt['foodName']} - {opt['price']:,.0f}đ")
            dispatcher.utter_message('\n'.join(lines))
        else:
            dispatcher.utter_message(text="Không có lựa chọn nào đang chờ.")
        return []
