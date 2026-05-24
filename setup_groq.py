"""حفظ مفتاح Groq في .env — شغّل: py setup_groq.py"""
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent
    env_path = root / ".env"
    print("الصق مفتاح Groq من https://console.groq.com/keys")
    print("(يبدأ بـ gsk_) ثم Enter:")
    key = input().strip()
    if not key.startswith("gsk_"):
        print("مفتاح غير صالح — لازم يبدأ بـ gsk_")
        return
    env_path.write_text(f"GROQ_API_KEY={key}\n", encoding="utf-8")
    size = env_path.stat().st_size
    print(f"تم الحفظ: {env_path}")
    print(f"حجم الملف: {size} bytes — لو 0 يبقى في مشكلة")

if __name__ == "__main__":
    main()
