using Microsoft.AspNetCore.Mvc;

namespace Example.Service.Controllers;

[ApiController]
[Route("api/[controller]")]
public class ThingsController : ControllerBase
{
    private readonly HttpClient httpClient;

    public ThingsController(HttpClient httpClient)
    {
        this.httpClient = httpClient;
    }

    [HttpGet("{id}")]
    public async Task<string> GetThing(string id)
    {
        await httpClient.GetAsync("http://inventory-service/inventory/" + id);
        await bus.Publish<ThingLoaded>();
        var query = BuildThingQuery(id);
        return query;
    }

    private string BuildThingQuery(string id)
    {
        return "EXEC dbo.get_thing_by_id";
    }
}
