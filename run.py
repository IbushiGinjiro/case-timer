# exe化（PyInstaller）でも動くよう、絶対importの入口を別に用意する
from app.main import main

if __name__ == "__main__":
    main()
