from ui import MainWindow
from logger import logger


def main():

    logger.start_session()

    logger.info("APP", "Application Started")

    app = MainWindow()

    app.run()

    logger.info("APP", "Application Closed")

    logger.end_session()


if __name__ == "__main__":
    main()