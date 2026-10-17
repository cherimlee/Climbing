// climbing-island 워커
// - 평소 요청: climbing-report/docs 정적 파일을 그대로 돌려줌 (맨 앞 주소 / 는 지도 /map 으로 보냄)
// - 예약 실행(Cron Triggers): GitHub Actions의 collect-somoim 워크플로를 깨움
//   09:30 KST 알람에서는 매월 25일·12월 15일·월요일이면 check-gyms(암장 정보 점검)도 깨움
//   GitHub 자체 예약(schedule)은 몇 시간씩 늦거나 건너뛰는 일이 잦아서, 정시에 도는 Cloudflare 크론으로 대신 호출함
//   필요한 비밀값: GH_TOKEN (cherimlee/Climbing 저장소 Actions 읽기/쓰기 권한이 있는 fine-grained 토큰)

const REPO = "cherimlee/Climbing";
const WORKFLOW = "collect.yml";
const CHECK_WORKFLOW = "check-gyms.yml";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/index.html") {
      return Response.redirect(new URL("/map" + url.search, url), 302);
    }
    return env.ASSETS.fetch(request);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env, WORKFLOW, { start_at: "auto" }));
    if (event.cron === "30 0 * * *") {
      // 00:30 UTC = 09:30 KST, 날짜는 한국 날짜와 같음. schedule 값은 check-gyms.yml의 GitHub 예약 줄과 맞춤
      const d = new Date(event.scheduledTime);
      const due = [];
      if (d.getUTCDate() === 25) due.push("17 5 25 * *");                        // 월간 점검
      if (d.getUTCMonth() === 11 && d.getUTCDate() === 15) due.push("17 5 15 12 *"); // 연말연시 점검
      if (d.getUTCDay() === 1) due.push("17 5 * * 1");                           // 명절 점검(시기가 아니면 바로 종료)
      for (const schedule of due) {
        ctx.waitUntil(dispatch(env, CHECK_WORKFLOW, { mode: "auto", schedule }));
      }
    }
  },
};

async function dispatch(env, workflow, inputs) {
  const res = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "climbing-cron",
    },
    body: JSON.stringify({ ref: "main", inputs }),
  });
  if (res.status !== 204) {
    throw new Error(`${workflow} dispatch failed: ${res.status} ${await res.text()}`);
  }
}
