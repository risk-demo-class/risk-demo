import pymysql
from app.config import settings

conn = pymysql.connect(
    host=settings.DB_HOST, port=settings.DB_PORT,
    user=settings.DB_USER, password=settings.DB_PASSWORD,
    database=settings.DB_NAME, charset='utf8mb4'
)
cur = conn.cursor()
cur.execute('SELECT COUNT(*), SUM(ml_score IS NULL), SUM(ml_score IS NOT NULL) FROM risk_assessment')
r = cur.fetchone()
print(f'Total: {r[0]}, ml_null: {r[1]}, ml_notnull: {r[2]}')

if r[2] > 0:
    cur.execute('UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL')
    print(f'Updated: {cur.rowcount} records')
    conn.commit()
else:
    print('All already NULL, nothing to clear')
conn.close()