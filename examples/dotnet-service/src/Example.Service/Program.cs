var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.MapPost("/things/{id}", (string id) => Results.Ok(new { id }));

app.Run();
