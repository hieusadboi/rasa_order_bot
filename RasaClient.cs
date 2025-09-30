using System;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

public class RasaClient
{
    private readonly HttpClient _client;
    private readonly string _url;

    public RasaClient(string url = "http://localhost:5005/webhooks/rest/webhook")
    {
        _client = new HttpClient();
        _url = url;
    }

    public async Task<JArray> SendMessageAsync(string message, string sender = "user1")
    {
        var payload = new
        {
            sender = sender,
            message = message
        };
        var content = new StringContent(JsonConvert.SerializeObject(payload), Encoding.UTF8, "application/json");
        var resp = await _client.PostAsync(_url, content);
        var str = await resp.Content.ReadAsStringAsync();
        return JArray.Parse(str);
    }
}
