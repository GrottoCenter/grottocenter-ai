import logging
from contextlib import asynccontextmanager

import pymongo
from fastapi import FastAPI

from client.HttpClient import httpClient
from config.settings import SettingsError, settings, validate_settings

logger = logging.getLogger(__name__)

# Fail a database call after a few seconds instead of the 30 s pymongo default,
# so /ready and requests answer quickly when MongoDB is down.
MONGO_SERVER_SELECTION_TIMEOUT_MS = 3000


def build_lifespan(config=settings, mongo_client_factory=pymongo.MongoClient):
    """Validate the settings, then own the MongoDB and GreenPT clients.

    Both clients are created at startup and closed at shutdown, so a request
    never has to build one.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        problems = validate_settings(config)
        if problems:
            raise SettingsError(problems)

        mongo_client = mongo_client_factory(
            config.mongo_uri,
            serverSelectionTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS,
        )
        app.state.mongo_client = mongo_client
        app.state.mongo_db = mongo_client[config.mongo_db_name]
        try:
            async with httpClient(app, config):
                yield
        finally:
            mongo_client.close()
            logger.info("MongoDB client closed")

    return lifespan
