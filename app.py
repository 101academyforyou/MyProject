"""客戶管理系統啟動程式。

用法：
    python3 app.py                 # 預設 http://127.0.0.1:8000
    python3 app.py --port 9000 --db data.db
"""

import argparse

from crm.server import create_server


def main():
    parser = argparse.ArgumentParser(description="客戶管理系統")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default="crm.db", help="SQLite 資料庫檔案路徑")
    args = parser.parse_args()

    server = create_server(args.db, args.host, args.port)
    print(f"客戶管理系統已啟動：http://{args.host}:{args.port}  （Ctrl+C 結束）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()
        server.db.close()


if __name__ == "__main__":
    main()
