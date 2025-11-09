import logging
import os

def setup_logger(node_id: int):
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"node_{node_id}.log")

    logger = logging.getLogger(f"node_{node_id}")
    logger.setLevel(logging.DEBUG)

    # Очистка предыдущих обработчиков, чтобы избежать дублирования логов
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)  # Установим уровень DEBUG для консоли

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
