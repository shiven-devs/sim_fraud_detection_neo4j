"""Neo4j access for the face service. Routes should use this instead of opening their own drivers."""

from __future__ import annotations

from contextlib import contextmanager

from neo4j import GraphDatabase

from .config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


@contextmanager
def session():
    db = get_driver().session()
    try:
        yield db
    finally:
        db.close()


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
