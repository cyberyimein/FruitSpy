# Room Climate MCP

FruitSpy exposes one read-only MCP tool:

```text
get_room_climate
```

It returns the latest temperature, relative humidity, CO2 concentration, sensor
battery level, observation time, sample age, and stale flag. The tool accepts no
arguments. FruitSpy does not retain climate history; each valid BLE reading
replaces the previous in-memory value.

## Endpoint and mode

```text
POST /api/v1/tools/room-climate/mcp
```

Choose the endpoint's active wire protocol on the FruitSpy API page:

- **New** (default): MCP `2026-07-28`
- **Compatible**: MCP `2025-11-25`

The selection is retained in the shared FruitSpy state file. Sensor readings are
not written there.

## Modern request

Modern MCP is stateless. Every request includes the protocol version, client
capabilities, and the required HTTP routing headers. `clientInfo` is recommended
by the final `2026-07-28` specification but may be omitted:

```http
POST /api/v1/tools/room-climate/mcp
Accept: application/json, text/event-stream
Content-Type: application/json
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: get_room_climate

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_room_climate",
    "arguments": {},
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientInfo": {
        "name": "personal-ai",
        "version": "1.0.0"
      },
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

The modern endpoint also implements `server/discover` and includes
`resultType: "complete"` in successful results.

## Compatible request sequence

In compatible mode, begin with the legacy initialization handshake:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-11-25",
    "capabilities": {},
    "clientInfo": {
      "name": "personal-ai",
      "version": "1.0.0"
    }
  }
}
```

Then send `notifications/initialized`, followed by `tools/list` or `tools/call`.
Post-initialization requests should include:

```http
MCP-Protocol-Version: 2025-11-25
```

## Authentication and browser safety

Set `FRUITSPY_ROOM_CLIMATE_MCP_TOKEN` to require:

```http
Authorization: Bearer <token>
```

The MCP endpoint rejects browser requests whose `Origin` does not match the HTTP
`Host`, protecting a local FruitSpy instance from DNS rebinding through a hostile
web page.
