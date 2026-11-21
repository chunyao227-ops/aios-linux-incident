FROM python:3.10-slim

RUN useradd --create-home --uid 1000 app

WORKDIR /opt/demo
COPY app/ /opt/demo/
RUN chmod +x /opt/demo/entrypoint.sh \
    && mkdir -p /etc/demo /var/lib/demo /run/demo \
    && chown -R app:app /etc/demo /var/lib/demo /run/demo /opt/demo

USER app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8080 6379

CMD ["/opt/demo/entrypoint.sh"]
