FROM python:3.10-slim

# Create user with UID 1000 (recommended standard for Hugging Face Spaces)
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PORT=7860

WORKDIR /app

# Copy application files and sample datasets
COPY --chown=user:user scopus_app/ /app/scopus_app/
COPY --chown=user:user university_list.xlsx INABIO_Publications_2024_Final.csv INABIO_Publications_2025_Standard.csv /app/
RUN chown -R user:user /app

USER user

EXPOSE 7860

CMD ["python3", "/app/scopus_app/app.py"]
