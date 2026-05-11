import fastify from "fastify";

const server = fastify();

server.get("/inventory/:id", async request => {
  return {
    id: request.params,
  };
});
