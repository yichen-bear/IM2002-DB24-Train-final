import sys
sys.path.insert(0, ".")

from databases.relational.queries import execute_booking, query_user_profile

# 1. 填入你剛剛在 UI 註冊的帳號 Email
user_email = "s@s"  

# 2. 查詢該使用者的 user_id
profile = query_user_profile(user_email)

if not profile:
    print("找不到該使用者，請確認 Email 是否正確。")
else:
    user_id = profile["user_id"]
    print(f"找到使用者！User ID: {user_id}")

    # 3. 手動呼叫 execute_booking 建立訂單
    success, result = execute_booking(
        user_id=user_id,
        schedule_id="NR_SCH01",           # 假設使用 NR_SCH01 班次
        origin_station_id="NR01",         # 起站 (Central)
        destination_station_id="NR05",    # 迄站 (Stonehaven)
        travel_date="2026-06-01",         # 搭乘日期
        fare_class="standard",            # 艙等 (standard 或 first)
        seat_id="any",                    # 交由系統自動派位
        ticket_type="single"              # 單程票
    )

    if success:
        print("\n✅ 訂單建立成功！")
        print(f"你的訂單編號 (Booking ID) 是: {result['booking_id']}")
        print(f"座位: {result['seat_id']}, 金額: ${result['amount_usd']}")
    else:
        print("\n❌ 訂單建立失敗：")
        print(result)