"""为 education_risk 补充 100 条可重复生成的教育业务数据。

运行：python scripts/gen_business_data.py
只插入 ID 以 edu_demo_ 开头的数据，因此可安全重复运行。
"""
from datetime import datetime, timedelta
from pathlib import Path
import random
import sys

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from app.config import settings  # noqa: E402


def main() -> None:
    conn = pymysql.connect(host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER,
                           password=settings.DB_PASSWORD, database=settings.DB_NAME, charset="utf8mb4")
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM enrollment WHERE enrollment_id LIKE 'edu_demo_%'")
            now = datetime.now()
            rows = []
            for i in range(100):
                user_id = "edu_001" if i % 5 else "edu_002"
                course_id = ["course_python", "course_ai", "course_math"][i % 3]
                amount = [999, 5999, 12999][i % 3]
                rows.append((f"edu_demo_{i:03d}", user_id, course_id, amount,
                             now - timedelta(days=i % 30, hours=i % 24), "已报名", "课程学习"))
            cur.executemany(
                "INSERT INTO enrollment (enrollment_id,user_id,course_id,total_amount,payment_time,status,study_goal) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)", rows,
            )
        conn.commit()
        print("已生成 100 条教育报名数据（education_risk.enrollment）")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
