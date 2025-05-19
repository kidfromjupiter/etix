import logging

def setup_logger(name, level=logging.DEBUG, logfile='./logs/logfile.log'):
    """
    Configure and return a logger with the specified name and level
    
    Args:
        name: Logger name
        level: Logging level
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if no handlers exist (prevent duplicate handlers)
    if not logger.handlers:
        logger.setLevel(level)

        # Create file handler
        handler = logging.FileHandler(logfile)
        handler.setLevel(level)

        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)

        # Add handler to logger

        logger.addHandler(handler)

    return logger

# Configure root logger by default
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)