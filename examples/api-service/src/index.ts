import fastify from "fastify";
import { formatThing } from "@example/shared";

const server = fastify();

export async function loadThing(id: string) {
  const response = await fetch(`/things/${id}`);
  await fetch(`${process.env.INVENTORY_SERVICE_URL}/inventory/${id}`);
  await producer.send({ topic: "things.changed", messages: [{ value: id }] });
  await s3.putObject({ Bucket: "shared-artifacts", Key: "things/report.json", Body: id });
  return response.json();
}

async function thingsRoute(request) {
  const query = "EXEC dbo.get_thing_by_id";
  await loadThing("42");
  return formatThing(query);
}

server.get("/things/:id", thingsRoute);
