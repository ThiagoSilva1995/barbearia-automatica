import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
import pytz
import sys

tz_br = pytz.timezone("America/Sao_Paulo")


class TimezoneFormatter(logging.Formatter):
    """Formatter que usa horário de Brasília"""
    def formatTime(self, record, datefmt=None):
        ct = datetime.fromtimestamp(record.created, tz_br)
        if datefmt:
            return ct.strftime(datefmt)
        return ct.isoformat()


def setup_logging():
    """Configura logging com rotação diária e saída em arquivo"""
    
    # Criar diretório de logs
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configuração do logger raiz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Limpar handlers existentes
    root_logger.handlers.clear()
    
    # Formato dos logs
    formatter = TimezoneFormatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler 1: Arquivo com rotação diária (mantém 30 dias)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "app.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=False
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Handler 2: Console (stdout) - mantém compatibilidade com Fly.io
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Handler 3: Arquivo de ERROS separado (mais fácil de investigar)
    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "errors.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=False
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    
    # Adicionar handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(error_handler)
    
    # Reduzir verbosidade de bibliotecas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    logging.info("📝 Sistema de logging configurado (rotação diária, 30 dias)")
