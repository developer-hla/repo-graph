CREATE TABLE dbo.things (
  id int not null
);

CREATE PROCEDURE dbo.get_thing_by_id AS
SELECT * FROM dbo.things;
UPDATE dbo.things SET id = id;
