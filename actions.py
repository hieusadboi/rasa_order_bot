# actions.py - Rasa custom actions connecting to SQL Server (Windows Auth)
from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker
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
    try:
        conn = pyodbc.connect(CONN_STR)
        print("DEBUG: Kết nối database thành công")
        return conn
    except Exception as e:
        print(f"DEBUG: Lỗi kết nối database: {e}")
        raise e
    
def clean_food_text(text):
    location_keywords = [
        'ở', 'tại', 'bàn', 'mang', 'về', 'nhé', 'ạ', 
        'cho', 'tôi', 'đi', 'nha', 'ấy', 'đó'
    ]
    cleaned = text
    for keyword in location_keywords:
        pattern = rf'\s*{re.escape(keyword)}\s+.*$'
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def search_foods(food_raw: str) -> List[Dict]:
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
        text = tracker.latest_message.get('text', '') or ''
        table = find_table_by_text(text)
        slot_events = [SlotSet('table_name', table)] if table else []

        # số lượng cơ bản
        nummap = { 'một':1,'mot':1,'1':1,'hai':2,'2':2,'ba':3,'3':3,'bốn':4,'4':4,'năm':5,'5':5 }
        pattern = re.compile(r"(?:(\d+|một|mot|hai|ba|bốn|nam|năm)\s+([\w\sàáạảãâầấậẩẫăằắặẳẵêềếệểễôơưứừữựếé]+?))(?=\s*(?:,|và|\.|$|ở|tại|bàn|mang|về))", flags=re.IGNORECASE)        
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
            food_raw = clean_food_text(m[1].strip())
            items.append({'food_raw': food_raw, 'quantity': qty})

        if not items:
            short_pattern = re.compile(r"(\d+)\s+([\w\s]+)", flags=re.IGNORECASE)
            m = short_pattern.search(text)
            if m:
                items.append({'food_raw': m.group(2).strip(), 'quantity': int(m.group(1))})

        if not items:
            ents = tracker.latest_message.get('entities', [])
            for e in ents:
                if e.get('entity') == 'food':
                    items.append({'food_raw': e.get('value'), 'quantity': 1})

        resolved = []
        pending_options = []
        for it in items:
            options = search_foods(it['food_raw'])
            if len(options) == 0:
                resolved.append({'food': it['food_raw'], 'quantity': it['quantity'], 'idFood': None})
            elif len(options) == 1:
                opt = options[0]
                resolved.append({'food': opt['foodName'], 'quantity': it['quantity'], 'idFood': opt['idFood'], 'price': opt['price']})
            else:
                pending_options.append({'raw': it['food_raw'], 'quantity': it['quantity'], 'options': options})

        if pending_options:
            po = pending_options[0]
            text_lines = [f"Có {len(po['options'])} món liên quan đến '{po['raw']}', bạn muốn món nào?\n"]
            for idx,opt in enumerate(po['options'], start=1):
                text_lines.append(f"{idx}. {opt['foodName']} - {opt['price']:,.0f}đ")
            text_lines.append("Vui lòng trả lời bằng số (ví dụ: 1) hoặc tên món.")
            dispatcher.utter_message('\n'.join(text_lines))
            slot_value = {'resolved': resolved, 'pending': pending_options, 'table': tracker.get_slot('table_name')}
            return slot_events + [SlotSet('pending_order', json.dumps(slot_value))]

        order_summary_parts = [f"{r['quantity']} {r['food']}" for r in resolved]
        order_summary = ' và '.join(order_summary_parts) if order_summary_parts else 'không có món rõ ràng'

        table_confirm = tracker.get_slot('table_name') or table or 'Mang về'
        if not table_confirm:
            table_confirm = 'Mang về'
            slot_events.append(SlotSet('table_name', table_confirm))

        payload = {
            'message': f"Dạ, bạn gọi {order_summary} tại {table_confirm}, đúng không ạ?",
            'order': resolved,
            'table': table_confirm,
            'status': 'pending_confirmation'
        }
        dispatcher.utter_message(text=payload['message'], json_message=payload)
        return slot_events + [SlotSet('pending_order', json.dumps({'resolved': resolved, 'pending': [], 'table': table_confirm}))]

class ActionConfirmOrder(Action):
    def name(self) -> Text:
        return "action_confirm_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        p = tracker.get_slot('pending_order')
        if not p:
            dispatcher.utter_message(text="❌ Không có đơn hàng nào để xác nhận.")
            return []

        payload = json.loads(p)
        resolved = payload.get('resolved', [])
        table_name = payload.get('table') or tracker.get_slot('table_name') or 'Mang về'

        if not resolved:
            dispatcher.utter_message(text="❌ Không có món ăn nào trong đơn để xác nhận.")
            return [SlotSet('pending_order', None), SlotSet('table_name', None)]

        conn, cur = None, None
        try:
            conn = db_connect()
            cur = conn.cursor()

            # đảm bảo có idTable
            cur.execute("SELECT idTable FROM TableFood WHERE tableName = ?", (table_name,))
            row = cur.fetchone()
            if row:
                idTable = int(row[0])
            else:
                cur.execute("INSERT INTO TableFood (tableName, status) VALUES (?, ?)", (table_name, 'Trống'))
                conn.commit()
                cur.execute("SELECT SCOPE_IDENTITY()")
                idTable = int(cur.fetchone()[0])

            # tạo bill
            createdBy = 'system_voice'
            cur.execute("""
                INSERT INTO Bill (DateCheckIn, idTable, status, createdBy)
                OUTPUT INSERTED.idBill
                VALUES (GETDATE(), ?, 0, ?)
            """, (idTable, createdBy))
            idBill = int(cur.fetchone()[0])

            # thêm món ăn
            for item in resolved:
                idFood = int(item['idFood'])
                qty = int(item.get('quantity', 1))
                cur.execute("SELECT count FROM BillInfo WHERE idBill = ? AND idFood = ?", (idBill, idFood))
                existing = cur.fetchone()
                if existing:
                    cur.execute("UPDATE BillInfo SET count = count + ? WHERE idBill = ? AND idFood = ?", (qty, idBill, idFood))
                else:
                    cur.execute("INSERT INTO BillInfo (idBill, idFood, count) VALUES (?, ?, ?)", (idBill, idFood, qty))

            conn.commit()
            valid_names = [f"{item.get('quantity', 1)} {item.get('food')}" for item in resolved]
            dispatcher.utter_message(
                text=f"✅ Đã lưu đơn thành công! Mã hóa đơn: {idBill}\n"
                     f"📦 Món đã đặt: {', '.join(valid_names)}\n"
                     f"🍽️ Bàn: {table_name}\n\n👉 Bạn có muốn gọi thêm món mới không?"
            )

        except Exception as e:
            import traceback
            print("🛑 ERROR confirm_order:", traceback.format_exc())
            dispatcher.utter_message(text=f"❌ Có lỗi khi lưu đơn: {str(e)}")
        finally:
            if cur: cur.close()
            if conn: conn.close()

        return [SlotSet('pending_order', None), SlotSet('table_name', None)]

class ActionCancelOrder(Action):
    def name(self) -> Text:
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(
            text="❌ Đơn hàng đã được huỷ.\n👉 Bạn có muốn bắt đầu gọi món mới không?"
        )
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
    

class ActionChangeOrder(Action):
    def name(self) -> Text:
        return "action_change_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        p = tracker.get_slot("pending_order")
        if not p:
            dispatcher.utter_message(text="❌ Hiện tại không có đơn hàng nào để sửa.")
            return []

        try:
            payload = json.loads(p)
        except Exception:
            dispatcher.utter_message(text="❌ Dữ liệu đơn hàng không hợp lệ.")
            return []

        resolved = payload.get("resolved", [])
        if not resolved:
            dispatcher.utter_message(text="❌ Đơn hàng trống, không có gì để sửa.")
            return []

        # Lấy entity mới từ câu nói (food + quantity)
        latest_food = next(tracker.get_latest_entity_values("food"), None)
        latest_qty = next(tracker.get_latest_entity_values("quantity"), None)

        if not latest_food:
            dispatcher.utter_message(text="⚠️ Bạn muốn đổi món nào?")
            return []

        # Tìm món trong order để sửa
        found = False
        for item in resolved:
            if latest_food.lower() in item["food"].lower():
                if latest_qty:
                    try:
                        qty = int(latest_qty)
                    except:
                        qty = 1
                    item["quantity"] = qty
                found = True
                break

        if not found:
            dispatcher.utter_message(text=f"⚠️ Trong đơn chưa có món {latest_food}. Bạn có muốn thêm mới không?")
            return []

        # Cập nhật slot pending_order
        payload["resolved"] = resolved
        new_payload = json.dumps(payload, ensure_ascii=False)

        dispatcher.utter_message(text=f"✅ Đã cập nhật lại đơn: {resolved}")
        return [SlotSet("pending_order", new_payload)]

