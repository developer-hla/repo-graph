CREATE TABLE dbo.things (
  id int not null
);
CREATE TABLE dbo.customers (
  id int not null
);
CREATE TABLE dbo.orders (
  customer_id int REFERENCES dbo.customers(id)
);

CREATE PROCEDURE dbo.get_thing_by_id AS
SELECT * FROM dbo.things;
UPDATE dbo.things SET id = id;
