import fastify from "fastify";
import { formatThing } from "@example/shared";

const server = fastify();

server.get("/things/:id", async () => {
  const query = "EXEC dbo.get_thing_by_id";
  return formatThing(query);
});
