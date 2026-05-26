Imports System.Configuration
Imports System.Data
Imports System.Data.SqlClient
Imports System.Net
Imports System.Web.Services

Namespace Example.Legacy
  Public Class LegacyOrderService
    <WebMethod()>
    Public Function GetOrder(id As Integer) As String
      Dim baseUrl = ConfigurationManager.AppSettings("InventoryServiceUrl")
      Dim request = WebRequest.Create("http://inventory-service/api/orders/" & id)
      Dim message = QueueClient.ReceiveAsync("legacy-orders")
      Dim report = File.ReadAllText("shared-artifacts/things/report.json")
      Dim cached = cache.GetString("thing:latest")
      Dim commandName = BuildCommandName(id)
      Dim command As New SqlCommand("dbo.GetOrder")
      command.CommandType = CommandType.StoredProcedure
      Return baseUrl
    End Function

    Private Function BuildCommandName(id As Integer) As String
      Return "dbo.GetOrder"
    End Function
  End Class
End Namespace
