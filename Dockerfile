# 1. ベースとなるPythonの環境を決定（軽量なslim版を使用）
FROM python:3.12-slim

# 2. コンテナ内の作業ディレクトリを「/app」に設定
WORKDIR /app

# 3. OSの必要なツールをインストール（FirebaseやGCP連携でのエラー防止）
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# 4. 依存ライブラリのリストをコンテナにコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. あなたが作ったソースコード（app.pyやstyle.cssなど）をすべてコンテナにコピー
COPY . .

# 6. Streamlitがコンテナ外（インターネット）からの接続を受け付けるためのポート設定
EXPOSE 8080

# 7. アプリを起動するコマンド（Cloud Runの仕様に合わせてポート8080で起動）
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]