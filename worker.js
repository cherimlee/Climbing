// climbing-island 워커
// - 평소 요청: climbing-report/docs 정적 파일을 그대로 돌려줌 (맨 앞 주소 / 는 지도 /map 으로 보냄)
// - 예약 실행(Cron Triggers): GitHub Actions의 collect-somoim 워크플로를 깨움
//   GitHub 자체 예약(schedule)은 몇 시간씩 늦거나 건너뛰는 일이 잦아서, 정시에 도는 Cloudflare 크론으로 대신 호출함
//   필요한 비밀값: GH_TOKEN (cherimlee/Climbing 저장소 Actions 읽기/쓰기 권한이 있는 fine-grained 토큰)

const REPO = "cherimlee/Climbing";
const WORKFLOW = "collect.yml";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/index.html") {
      return Response.redirect(new URL("/map" + url.search, url), 302);
    }
    if (url.pathname === "/token-check") {
      return Response.json(await checkToken(env));
    }
    return env.ASSETS.fetch(request);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },
};

async function dispatch(env) {
  const res = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${(env.GH_TOKEN || "").trim()}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "climbing-cron",
    },
    body: JSON.stringify({ ref: "main", inputs: { start_at: "auto" } }),
  });
  if (res.status !== 204) {
    throw new Error(`workflow dispatch failed: ${res.status} ${await res.text()}`);
  }
}

// 토큰 값은 보여주지 않고, 제대로 들어갔는지만 확인 (GitHub에 저장소 읽기만 해봄)
async function checkToken(env) {
  const raw = env.GH_TOKEN || "";
  const token = raw.trim();
  const res = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "climbing-cron",
    },
  });
  return {
    has_token: raw.length > 0,
    length: token.length,
    starts_with_github_pat: token.startsWith("github_pat_"),
    had_extra_spaces: raw !== token,
    github_status: res.status,
    ok: res.status === 200,
  };
}
