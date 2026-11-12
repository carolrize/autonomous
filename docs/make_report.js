// 중간 보고서 .docx 생성: node docs/make_report.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, AlignmentType, ImageRun, LevelFormat, BorderStyle, PageBreak,
  Footer, PageNumber,
} = require("docx");

const FONT = "Malgun Gothic";
const ACCENT = "1F4E79";
const W = 9026; // A4 본문 폭 (DXA, 여백 1인치)

const p = (text, opts = {}) => new Paragraph({
  spacing: { after: 100, line: 300 }, ...opts,
  children: Array.isArray(text) ? text : [new TextRun({ text, font: FONT, size: 21 })],
});
const t = (text, o = {}) => new TextRun({ text, font: FONT, size: 21, ...o });
const b = (text) => t(text, { bold: true });
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text, font: FONT })] });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text, font: FONT })] });
const bullet = (runs, level = 0) => new Paragraph({
  numbering: { reference: "bul", level }, spacing: { after: 60, line: 290 },
  children: typeof runs === "string" ? [t(runs)] : runs,
});
const num = (runs, ref = "num") => new Paragraph({
  numbering: { reference: ref, level: 0 }, spacing: { after: 60, line: 290 },
  children: typeof runs === "string" ? [t(runs)] : runs,
});
const caption = (text) => new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { before: 60, after: 200 },
  children: [new TextRun({ text, font: FONT, size: 18, color: "555555" })],
});

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
function table(header, rows, widths, opts = {}) {
  const total = widths.reduce((a, c) => a + c, 0);
  const cell = (text, i, head, bold) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    borders: { top: border, bottom: border, left: border, right: border },
    shading: head ? { type: ShadingType.CLEAR, color: "auto", fill: "DCE6F1" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: String(text).split("\n").map((line) => new Paragraph({
      spacing: { after: 0, line: 260 },
      alignment: i === 0 || opts.left ? AlignmentType.LEFT : AlignmentType.CENTER,
      children: [new TextRun({ text: line, font: FONT, size: 18, bold: head || bold })],
    })),
  });
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r) => new TableRow({
        children: r.map((c, i) => cell(c, i, false, opts.boldRow && opts.boldRow(r))),
      })),
    ],
  });
}
const gap = () => new Paragraph({ spacing: { after: 120 }, children: [] });
const img = (file, w, h) => new Paragraph({
  alignment: AlignmentType.CENTER,
  children: [new ImageRun({ type: "png", data: fs.readFileSync(file), transformation: { width: w, height: h } })],
});

const root = path.join(__dirname, "..");
const fig = path.join(root, "study/results/frontier_final_test.png");

const body = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 600, after: 120 },
    children: [new TextRun({ text: "뉴런 역치 기반 V2V 위험 정보 전달", font: FONT, size: 40, bold: true, color: ACCENT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 },
    children: [new TextRun({ text: "역치 필터링의 한계 분석과 위험도 인지 경합 릴레이(RAC-U) 제안", font: FONT, size: 26 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 },
    children: [new TextRun({ text: "중간 보고서 · 2026년 11월 12일 · 김규민", font: FONT, size: 20, color: "666666" })] }),

  h1("요약"),
  p([t("선행 탐구에서는 뉴런의 실무율을 모방해 각 차량이 자기 위험도 R이 역치 T를 넘을 때만 경고를 전달하게 했다. 이번 연구에서 이 방식을 다중 홉 전달 관점에서 다시 검증한 결과, "),
    b("급정거 직후에는 경고가 끊기고(도달률 0.64) 몇 초 뒤에는 flooding과 비슷한 양의 메시지를 쓰는"), t(" 두 가지 문제가 확인되었다.")]),
  p([t("이를 해결하기 위해 "), b("반응 결정(뉴런 역치)과 재전송 결정(경합 타이머)을 분리"), t("하고, 기존 거리 우선 경합 방식 위에 "),
    b("긴급도 기반 신뢰도 예산"), t("과 "), b("그래프 학습 기반 결정성 힌트"), t("를 더한 RAC-U를 제안하였다.")]),
  bullet([b("전달 성능: "), t("손실 0%에서 거리 타이머 대비 메시지 26% 감소(도달률 동일, p=9e-40), 손실 30%에서 고위험 차량 도달률 +1.5%p(p=9e-4, flooding 수준)")]),
  bullet([b("안전 평가: "), t("highway-env에서 경고가 TTC 1.5 s 미만 노출을 86% 줄이고(p=0.004) 충돌을 5/40 → 0/40으로 줄임")]),
  bullet([b("한계: "), t("손실 30%에서는 거리 타이머보다 메시지를 더 쓰며, 현재 시나리오에서는 경고 방식 간 안전 지표 차이가 나타나지 않음(포화)")]),

  h1("1. 연구 배경"),
  h2("1.1 문제"),
  p("자율주행차는 센서로 볼 수 없는 위험을 V2V 통신으로 공유받는다. 차량이 많아지면 메시지가 폭증해 채널이 혼잡해지므로, 무엇을 누가 보낼지 골라야 한다."),
  h2("1.2 선행 탐구"),
  p("각 차량이 위험도 R = w1·f_d(거리) + w2·f_v(접근속도) + w3·f_τ(TTC)를 계산하고, R ≥ T일 때만 반응·전달하게 하였다. 가중치와 역치는 유전 알고리즘으로 찾았다(정규화 가중치 0.13/0.65/0.22, T = 0.163)."),
  h2("1.3 선행 탐구의 한계"),
  p("각 차량이 자기 위험만 보고 판단하므로, 위험 지점에서 먼 중간 차량이 경고를 넘기지 않으면 그 뒤 차량 전체가 경고를 받지 못한다. 또한 직접 만든 환경과 선택 편향(GA 최고 개체 성능 보고) 때문에 재검증이 필요했다."),

  h1("2. 연구 질문과 진행 상태"),
  table(["연구 질문", "상태", "핵심 결과"], [
    ["RQ1 역치 필터링이 다중 홉 전달을 끊는가", "확인", "급정거 직후 도달률 0.64, 시간이 지나면 메시지 76~79%(flooding 대비)"],
    ["RQ2 적은 메시지로 같은 도달률", "부분 확인", "손실 0%에서 거리 타이머 대비 메시지 −26%, 도달률 동일"],
    ["RQ3 손실·조건 변화에 강건한가", "부분 확인", "손실 30% 고위험 도달 +1.5%p, 대신 메시지 증가. 미학습 밀도 일반화는 미실시"],
    ["RQ4 충돌 감소로 이어지는가", "1차 완료", "경고 시 위험 노출 −86%, 충돌 5/40 → 0/40. 방식 간 안전 차이는 없음"],
  ], [2900, 1100, 5026]),
  gap(),

  h1("3. 실험 환경"),
  table(["항목", "설정"], [
    ["전달 성능 실험", "Python 이벤트 기반 시뮬레이터. 편도 3차선 2 km, 차량 무작위 배치"],
    ["변수", "밀도 15/30/50대/km, 통신 반경 100/150/300 m, 패킷 손실 0/10/30%"],
    ["사건", "맨 앞 차량 급정거(−6 m/s²), 후방 500 m가 영향 범위"],
    ["안전 실험", "highway-env 1.12.1, 3차선, 1초마다 경고 반복, 경고에 따라 차량 반응"],
    ["시드 분리", "검증 0~29 · 학습 100~449 · 테스트 500~529, 600~629, 700~729 (튜닝 후에만 사용)"],
    ["지표", "영향 차량 도달률, 고위험 차량(정지거리 안) 도달률, 재전송 수, 제때 경고율, TTC<1.5 s 노출 시간, 충돌"],
    ["통계", "같은 시드 대응 비교 Wilcoxon 부호순위 검정, 충돌은 Fisher 정확 검정"],
  ], [2200, 6826], { left: true }),
  gap(),
  p([t("도달률은 '그래프상 도달 가능한 영향 차량' 기준으로 계산하였다. 반경 100 m에서는 영향 차량 전부가 연결된 경우가 59%뿐이어서, 이를 분리하지 않으면 어떤 방식도 고칠 수 없는 단절이 결과에 섞이기 때문이다.")]),

  h1("4. 기존 접근의 재검토"),
  p("최초 계획(역치 + GNN이 BFS 정답 라벨을 따라 릴레이 여부를 분류)을 실험으로 점검한 결과, 다음 문제가 확인되었다."),
  table(["확인된 문제", "근거"], [
    ["역치로 재전송을 정하면 두 번 실패", "급정거 직후 도달 0.51, 2초 뒤 재전송 14.5회(flooding 15.1회)"],
    ["BFS 정답 라벨이 단순 규칙보다 나쁨", "손실 0% 재전송: 정답 라벨 4.2 > MPR 3.7 > 2홉 커버리지 규칙 3.5"],
    ["미리 정한 릴레이 집합은 손실에 약함", "손실 30% 도달: MPR 0.59, 정답 라벨 0.66, 거리 타이머 0.90"],
    ["핵심 대조군은 MPR이 아니라 거리 타이머", "반응형(듣고 취소) 구조라 손실에 강함"],
    ["지연 차이는 의미 없음", "방식 간 차이 2~8 ms, TTC(초 단위) 대비 무시 가능"],
  ], [3600, 5426], { left: true }),
  gap(),
  p([t("원인은 '나에게 위험한가'(반응)와 '내가 보내야 다른 차량이 받는가'(망 역할)를 위험도 R 하나로 판단한 데 있었다. 이에 따라 "), b("두 결정을 분리"), t("하는 방향으로 설계를 바꾸었다.")]),

  h1("5. 제안 방법: RAC-U"),
  h2("5.1 역할 분리"),
  table(["결정", "담당", "근거"], [
    ["반응 (감속·차선변경)", "뉴런 역치 R ≥ T (선행 탐구 유지)", "나에게 위험한가"],
    ["재전송", "RAC-U 경합 타이머", "내가 보내야 다른 차량이 받는가"],
  ], [2600, 3400, 3026]),
  gap(),
  h2("5.2 동작"),
  num([b("대기: "), t("경고를 받은 차량은 대기 시간 = TMAX × (1 − 우선순위)만큼 기다린다. 송신자에게서 뒤로 멀수록 먼저 보낸다.")]),
  num([b("측면 억제: "), t("기다리는 동안 자기보다 뒤에 있는 차량의 재전송을 k번 들으면 취소한다.")]),
  num([b("긴급도 기반 신뢰도 예산: "), t("정지 여유 m = (급정거 지점까지 거리 − 정지거리)/속도로 목표 누락확률 ε를 정하고(m<0이면 0.01, m<2 s면 0.05), k = ⌈log ε / log p⌉로 계산한다. 손실이 없으면 k=1, 손실이 크면 위험한 곳만 중복이 늘어난다.")]),
  num([b("학습 결정성 힌트: "), t("2홉 그래프 모델(SIGN 방식, 자기·1홉·2홉 평균 특징 30개 → MLP)이 '이 차량이 빠지면 경고가 끊길 확률'을 예측하고, 0.05 이상이면 우선순위를 높이고 가지치기에서 제외한다. 라벨은 패킷 손실을 무작위로 적용한 그래프에서 해당 차량을 지웠을 때 끊기는 영향 차량 비율의 기대값이다.")]),
  num([b("가지치기: "), t("손실이 5% 미만이고 새로 덮을 차량이 0.5대 미만이면 재전송하지 않는다.")]),
  p([t("뉴런 비유: 대기 시간은 막전위 상승, 다른 차량의 재전송은 억제 입력(측면 억제), 긴급도는 억제를 견디는 문턱에 해당한다.")]),

  h1("6. 선행연구 대비"),
  table(["구성요소", "비슷한 선행연구", "판단"], [
    ["거리 우선 대기 + 들으면 취소", "CBF, slotted 1-persistence(Wisitpongphan 2007), EMDV, MERL", "겹침 (기반·인용)"],
    ["새 커버리지 작으면 재전송 안 함", "Ni et al. 1999, Rossi et al. 2008", "겹침"],
    ["밀도·중복 적응", "RBP 등 밀도 적응 확률 재전송", "부분 겹침"],
    ["GNN 릴레이 선택", "Galliera 2023(GAT+MARL), Amati 2026(GINE)", "부분 겹침 (여부 직접 출력 vs 타이머 힌트)"],
    ["정지거리 긴급도로 중복 횟수 결정", "검색에서 발견 못 함", "새로움"],
    ["손실 실현 그래프의 기대 결정성 라벨", "검색에서 발견 못 함", "새로움"],
    ["관련성 필터가 다중 홉을 끊는다는 정량 분석", "검색에서 발견 못 함", "새로움"],
    ["충돌까지 평가", "기존 연구는 도달률·지연 위주", "새로움"],
  ], [3100, 4026, 1900]),
  gap(),
  p("선행연구 검토는 웹 검색 수준이며, IEEE Xplore·KCI·RISS 확인이 남아 있다."),

  h1("7. 결과"),
  h2("7.1 전달 성능 (처음 사용한 테스트 시드 700~729, 810쌍)"),
  table(["패킷 손실", "방식", "도달률", "고위험 도달률", "메시지(flooding 대비)"], [
    ["0%", "RAC-U", "1.000", "1.000", "0.302"],
    ["", "거리 타이머", "1.000", "1.000", "0.396"],
    ["10%", "RAC-U", "0.980", "0.996", "0.534"],
    ["", "거리 타이머", "0.977", "0.989", "0.441"],
    ["30%", "RAC-U", "0.919", "0.969", "0.660"],
    ["", "거리 타이머", "0.902", "0.954", "0.502"],
    ["", "flooding", "0.933", "0.968", "1.000"],
  ], [1400, 2000, 1600, 1900, 2126]),
  gap(),
  bullet("손실 0%: 메시지 −1.02회(p=9e-40), 도달률 동일"),
  bullet("손실 10%: 도달률 차이 없음(p=0.37), 메시지는 더 사용"),
  bullet("손실 30%: 도달률 +1.7%p(p=0.001), 고위험 도달 +1.5%p(p=9e-4, flooding과 같은 수준), 메시지는 flooding의 66%"),
  img(fig, 600, 185),
  caption("그림 1. 패킷 손실률별 도달률–재전송 트레이드오프 (테스트 시드 500~529, 왼쪽 위가 좋음)"),
  h2("7.2 구성요소 제거 실험 (테스트 시드 500~529)"),
  p("선행 기법 조합(거리+커버리지 타이머, 가지치기)을 기준으로 새 요소를 하나씩 더했다."),
  table(["추가 요소", "도달률 변화", "고위험 도달 변화", "재전송 변화"], [
    ["+ 학습 결정성", "+0.008 (p=0.004)", "+0.004 (p=0.07)", "+0.18회"],
    ["+ 긴급도 예산", "+0.006 (p=0.002)", "+0.008 (p=2e-4)", "+0.71회"],
    ["둘 다 (RAC-U)", "+0.014 (p=1e-4)", "+0.013 (p=2e-5)", "+0.92회"],
  ], [2400, 2200, 2400, 2026]),
  gap(),
  p("두 새 요소 모두 선행 기법 조합 위에서 유의한 기여를 보였다. 이 실험은 D1 설정(가지치기 상시)으로 수행하였다."),
  h2("7.3 highway-env 안전 평가 (40시드)"),
  p("가정: 차간 시간 0.6 s, 경고 못 받은 차량은 앞차 급감속을 1.0 s 늦게 인지하고 최대 4 m/s²로 제동, 경고 받은 차량은 역치 규칙으로 선제 감속하고 최대 6 m/s² 제동. 전달 범위는 500 m + 20 m/s × 경과 시간으로 확장."),
  table(["방식", "TTC<1.5 s 노출(차량·초)\n손실 0% / 30%", "충돌 에피소드", "재전송\n손실 0% / 30%"], [
    ["경고 없음", "0.68", "5/40", "0"],
    ["역치 방식", "0.12 / 0.17", "0/40", "180 / 160"],
    ["거리 타이머", "0.095 / 0.095", "0/40", "106 / 130"],
    ["RAC-U", "0.095 / 0.095", "0/40", "96 / 154"],
    ["flooding", "0.095 / 0.095", "0/40", "308 / 290"],
  ], [2200, 2600, 1800, 2426]),
  gap(),
  bullet("경고 방식은 경고 없음 대비 노출 −86%(p=0.004). 민감도 조건(차간 0.8 s, 반응 지연 0.7 s)에서 충돌 7/40 → 0/40(Fisher p=0.012)"),
  bullet([b("전달 범위를 500 m로 고정하면 역치 방식의 노출은 0.69로 경고 없음(0.68)과 같아 안전 효과가 없었다."), t(" 범위를 넓혀야 효과가 생겼다.")]),
  bullet("RAC-U·거리 타이머·flooding은 안전 지표가 같아(포화) 차이는 메시지 효율에서만 나타났다. RAC-U는 손실 0%에서 거리 타이머보다 재전송 −9.9회(p=4e-8), 손실 30%에서는 +24회."),

  h1("8. 한계"),
  bullet("MAC 계층 충돌·은닉 단말을 모델링하지 않은 이상적 채널, 링크 손실은 독립 무작위"),
  bullet("급정거 1회, 3차선 시나리오만 평가. 현재 조건에서는 경고 방식 간 안전 차이가 드러나지 않음"),
  bullet("경고 못 받은 차량의 반응 지연·제동 한계는 가정값이며 결과가 이에 따라 달라짐"),
  bullet("GNN은 실행 환경 제약으로 PyTorch 대신 SIGN 방식 + MLP(sklearn)로 구현"),
  bullet("손실 30%에서는 거리 타이머보다 메시지를 더 사용(모든 조건에서 우세하지 않음)"),
  bullet("선행연구 검토가 웹 검색 수준"),

  h1("9. 향후 계획"),
  num("더 어려운 안전 시나리오(다중 급정거, 고밀도, 반응 지연 1.5 s)로 방식 간 안전 차이 확인", "num2"),
  num("학습에 없던 밀도·4차선 도로에서 일반화 실험", "num2"),
  num("PyTorch Geometric GraphSAGE로 교체 여부 결정(개인 PC)", "num2"),
  num("IEEE Xplore·KCI·RISS 선행연구 최종 확인", "num2"),
  num("논문 초고와 발표 자료 갱신", "num2"),

  h1("부록: 코드와 재현"),
  table(["파일", "내용"], [
    ["study/core.py", "이벤트 기반 다중 홉 전파 시뮬레이터"],
    ["study/policies.py", "전달 정책 (flooding, 역치, MPR, 거리 타이머, counter, RAC, RAC-U 등)"],
    ["study/gnn_lite.py", "SIGN 방식 그래프 모델 학습, 기대 결정성 라벨"],
    ["study/tune.py, final_eval.py, ablation.py", "파라미터 탐색, 테스트 시드 평가, 제거 실험"],
    ["study/hw_safety.py", "highway-env 안전 평가 (반응·충돌)"],
    ["study/live.py", "실시간 비교 뷰어 (브라우저 localhost:8000)"],
    ["study/CYCLES.md", "모든 실험 사이클 기록"],
  ], [3600, 5426], { left: true }),
];

const doc = new Document({
  creator: "김규민",
  title: "뉴런 역치 기반 V2V 위험 정보 전달 - 중간 보고서",
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 28, bold: true, color: ACCENT },
        paragraph: { spacing: { before: 320, after: 140 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 23, bold: true, color: "333333" },
        paragraph: { spacing: { before: 200, after: 100 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 500, hanging: 260 } } } }] },
      { reference: "num2", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 500, hanging: 300 } } } }] },
      { reference: "num", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 500, hanging: 300 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18, color: "888888" })] })] }) },
    children: body,
  }],
});

const out = path.join(__dirname, "V2V_연구_중간보고서_20261112.docx");
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(out, buf); console.log("saved", out); });
