import os

import requests
from example_python_shared import format_thing
from fastapi import APIRouter, FastAPI
from sqlalchemy import text

app = FastAPI()
router = APIRouter()


consumer = object()


class Worker:
    def fetch_inventory(self, thing_id: str) -> dict[str, str]:
        response = requests.get(f"{os.environ['INVENTORY_SERVICE_URL']}/inventory/{thing_id}")
        return response.json()


@router.get("/things/{thing_id}")
async def read_thing(thing_id: str) -> dict[str, str]:
    Worker().fetch_inventory(thing_id)
    consumer.subscribe(["things.changed"])
    query = text("EXEC dbo.get_thing_by_id")
    return format_thing(str(query))


app.include_router(router)
