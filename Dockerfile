FROM python:3.10-slim

# Create user with UID 1000 (recommended standard for Hugging Face Spaces)
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PORT=10000

WORKDIR /app

# Copy application files and institutional reference metadata
COPY --chown=user:user scopus_app/ /app/scopus_app/
COPY --chown=user:user university_list.xlsx /app/
RUN chown -R user:user /app

USER user

EXPOSE 10000

CMD ["python3", "/app/scopus_app/app.py"]
