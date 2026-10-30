import assert from "node:assert/strict";
import test from "node:test";
import { apiAnsweredAt, apiCacheClear, apiSharedGet } from "./jsonCache.ts";

test("the engine's last answer is remembered per path, a failure does not move it", async () => {
  apiCacheClear();
  assert.equal(apiAnsweredAt("/live.json"), undefined);
  const before = Date.now();
  await apiSharedGet("/live.json", async () => ({ status: "playing" }));
  const at = apiAnsweredAt("/live.json");
  assert.ok(at != null && at >= before && at <= Date.now());
  await assert.rejects(
    apiSharedGet("/live.json", async () => {
      throw new Error("injoignable");
    }),
  );
  assert.equal(apiAnsweredAt("/live.json"), at);
  assert.equal(apiAnsweredAt("/autodj/conducteur.json"), undefined);
  apiCacheClear();
  assert.equal(apiAnsweredAt("/live.json"), undefined);
});
