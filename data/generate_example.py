import random

# ===== Danh sách dữ liệu =====
foods = [
    "Cơm Tấm Sường Bì Chả", "Cơm Gà Xối Mỡ", "Phở Bò", "Bún Bò Huế",
    "Mì Xào Hải Sản", "Lẩu Thái Hải Sản", "Lẩu Gà Lá É", "Cá Chiên Sốt Cà",
    "Gà Chiên Nước Mắm", "Chả Giò", "Bò Xào Rau Muống", "Mực Xào Sa Tế",
    "Tôm Hấp Nước Dừa", "Trứng Hấp Thịt Bằm", "Canh Chua Cá Lóc",
    "Canh Rau Ngót Thịt Bằm", "Cơm Chay Thập Cẩm", "Đậu Hũ Kho Tộ",
    "Trà Đá", "Nước Mía", "Nước Suối", "Coca Cola", "Pessi",
    "Trà Bí Đao Đống Chai", "Kem Sữa", "Bánh Flan", "Rau Câu Dừa",
    "Kem Dừa", "Cơm Thêm", "Mì Gói", "Bún thêm"
]

tables = [
    "Bàn 1","Bàn 2","Bàn 3","Bàn 4","Bàn 5","Bàn 6","Bàn 7","Bàn 8",
    "Bàn 9","Bàn 10","Bàn Vip 1","Bàn Vip 2","Bàn Vip 3","Bàn Vip 4",
    "Bàn Vip 5","Mang về","Bàn Vip 6","Bàn VIP 7"
]

quantities_num = [str(i) for i in range(1, 21)]
quantities_text = ["một","hai","ba","bốn","năm","sáu","bảy","tám","chín","mười"]
quantities = quantities_num + quantities_text

def random_quantity(): return f"[{random.choice(quantities)}](quantity)"
def random_food(): return f"[{random.choice(foods)}](food)"
def random_table(): return f"[{random.choice(tables)}](table)"

# ===== Các intent generator =====
def gen_order_food():
    templates = [
        "cho tôi {q} {f} {t}",
        "lấy {q} {f} {t}",
        "{q} {f} {t}",
        "cho {t} {q} {f}",
        "{q} {f}",
        "cho tôi {q} {f}",
        "lấy {f} {t}",
        "cho tôi {f}",
        "{f}"
    ]
    return random.choice(templates).format(q=random_quantity(), f=random_food(), t=random_table())

def gen_add_item(): return f"thêm {random_quantity()} {random_food()}"
def gen_remove_item(): return f"bỏ {random_food()} đi"
def gen_change_quantity(): return f"đổi {random_food()} thành {random_quantity()}"
def gen_change_table(): return f"chuyển qua {random_table()}"
def gen_cancel_order(): return random.choice(["hủy hết", "xóa toàn bộ đơn hàng", "không lấy nữa"])
def gen_confirm(): return random.choice(["đúng rồi", "ok", "vâng", "chuẩn rồi"])
def gen_deny(): return random.choice(["không", "sai rồi", "đổi món khác"])
def gen_greet(): return random.choice(["xin chào", "hello", "hi", "chào bạn"])
def gen_goodbye(): return random.choice(["tạm biệt", "bye", "hẹn gặp lại"])
def gen_ask_menu(): return random.choice(["cho tôi xem menu", "có những món gì?", f"có {random_food()} không?"])
def gen_ask_price(): return f"giá {random_food()} bao nhiêu?"

# ===== Config intent =====
intent_config = {
    "order_food": (gen_order_food, 300000),
    "add_item": (gen_add_item, 300000),
    "remove_item": (gen_remove_item, 8000),
    "change_quantity": (gen_change_quantity, 8000),
    "change_table": (gen_change_table, 5000),
    "cancel_order": (gen_cancel_order, 3000),
    "confirm": (gen_confirm, 500),
    "deny": (gen_deny, 500),
    "greet": (gen_greet, 500),
    "goodbye": (gen_goodbye, 500),
    "ask_menu": (gen_ask_menu, 2000),
    "ask_price": (gen_ask_price, 2000),
}

# ===== Generate file NLU =====
def generate_nlu(filename="data/nlu.yml"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write('version: "3.1"\n')
        f.write("nlu:\n")
        for intent, (generator, target_count) in intent_config.items():
            examples = set()
            # thử nhiều lần, tránh thiếu
            for _ in range(target_count * 10):
                examples.add(generator())
                if len(examples) >= target_count:
                    break
            print(f"✅ {intent}: yêu cầu {target_count}, thực tế {len(examples)}")
            f.write(f"- intent: {intent}\n")
            f.write("  examples: |\n")
            for ex in examples:
                f.write(f"      - {ex}\n")

if __name__ == "__main__":
    generate_nlu()
