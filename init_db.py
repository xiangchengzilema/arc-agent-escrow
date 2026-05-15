"""初始化数据库"""

from escrow_engine import EscrowEngine

def main():
    engine = EscrowEngine("escrow.db")
    stats = engine.get_stats()
    print(f"Database initialized. Jobs: {stats['total_jobs']}")

if __name__ == "__main__":
    main()
