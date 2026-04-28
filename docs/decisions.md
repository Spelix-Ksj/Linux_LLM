# 워크샵 발표자료 제작 — 2026-04-27

## Task
- **요청:** ALIS/trunk 및 TPDemo/trunk의 최적화 알고리즘 분석 파일 4건을 기반으로 워크샵 발표자료(PPT) 제작
- **분석 파일:**
  - `D:\Dev\Spelix\Linux_LLM\docs\Kshift_Analysis_Reporting.md`
  - `D:\Dev\Spelix\Linux_LLM\docs\Kshift_Analysis_Reporting2.md`
  - `D:\Dev\Spelix\Linux_LLM\docs\Kshift_Analysis_Reporting2_withLP.md`
  - `D:\Dev\Spelix\Linux_LLM\docs\appendix_claude_cli_controller.md`
- **원본 소스:** `D:\Dev\ALIS\trunk`, `D:\Dev\TPDemo\trunk`

## Task Type
`mixed` — research(도구 조사) + docs(발표자료 작성)

## Team
- **Researcher A** (Explore): 분석 파일 4건의 핵심 내용 추출 및 슬라이드 구조 후보 제안
- **Researcher B** (Explore): PPT 제작에 사용 가능한 Skill/MCP/Plugin 조사 및 비교
- **Architect** (Plan): 두 리서치 결과 통합, 발표자료 제작 전략 및 슬라이드 아웃라인 설계
- **Implementer** (general-purpose): 선정된 도구로 실제 발표자료 제작 — 사용자 승인 후 spawn
- **Reviewer** (general-purpose): 결과물 품질 검토

## Key Decisions
- (PHASE 1) Researcher A/B 병렬 dispatch — 완료
- **도구 선정 (Auto mode 자동결정):** 1순위 `ecc:frontend-slides` (HTML 기반) + 2순위 `Gemini MCP`(필요 시 다이어그램 이미지 생성)
  - 근거: 단일 .html 파일 → 오프라인/온라인 즉시 공유, 애니메이션 풍부, 의존성 0, python-pptx 미설치 환경
- **출력 산출물:** `D:\Dev\Spelix\Linux_LLM\docs\Kshift_Workshop_Presentation.html` (단일 HTML 슬라이드 덱)
- **발표 컨셉:** "왜 해가 없을까? — KSHIFT 최적화 Infeasibility 원인 규명과 해결 전략" (Researcher A 제안)
- **슬라이드 분량:** 25슬라이드 (개요3 + 비교5 + 분석7 + 해결4 + 리포팅3 + 기술2 + 결론1)
- **데이터 마스킹 정책 (필수):**
  - 실제 프로젝트 번호/COMPANY_NO/CASE_NO → "프로젝트 A" 등 익명화
  - LP 파일 원본 경로/내용 노출 금지
  - 코드는 메서드명·클래스명만, 라인 번호 미공개
- **언어:** 한국어 (영문 용어 병기)

## Researcher A 결과 (콘텐츠 큐레이션)
- 4개 파일은 하나의 진단 스토리 (리포팅 격차 → 가설 → LP로 확정)
- **핵심 메시지:** "설계-구현 불일치" — DB는 SCD002=Soft, 코드는 Hard로 구현 → Infeasibility의 근본 원인
- **수치 요약:** MUL_WGT 1,658톤 > DAY_CAPA 200톤 → 수학적 해 불가능 / 11개 프로젝트 동일 영향 / SCD000×1 + SCD002×10
- **즉시 조치:** SCD002를 Soft 제약으로 전환 (3~5일)
- **장기 개선:** 자동 진단 다이얼로그 + 리포팅 패널 + Before/After 그리드 (~15일)

## Researcher B 결과 (도구 비교)
| 도구 | 종합 |
|------|------|
| frontend-slides | 4.6/5 ★ |
| Gemini MCP | 4.0/5 |
| investor-materials | 3.6/5 |
| google-workspace-ops | 3.5/5 |
| python-pptx | 2.5/5 (미설치) |

권장 워크플로: 분석 정리 → (선택)Gemini로 다이어그램 → frontend-slides로 HTML 생성 → 브라우저 검증.

## Implementer 결과
- **산출물:** `D:\Dev\Spelix\Linux_LLM\docs\Kshift_Workshop_Presentation.html` (102.4 KB, 2,204 라인)
- **슬라이드:** 25개 (id="slide-1" ~ "slide-25")
- **외부 의존성:** 0 (CSS/JS 모두 inline, http(s) 외부 링크 0건)
- **인터랙션:** 키보드(←→/Space/PgUp/PgDn/Home/End/ESC/N/T), 다크/라이트 토글, 발표자 노트
- **마스킹 적용:** Block #1~#11 익명화, LP 파일명/CASE_NO/COMPANY_NO/라인번호 0건 노출

## Reviewer 결과: PASS
- 9개 체크리스트 모두 충족 (단일 HTML, 25 슬라이드, 한국어+영문, 마스킹, 핵심 메시지, 시각요소, 키보드, 다크모드, 이모지 미사용)
- 마스킹 위반 패턴 0건 (`plan_MP1002_`, `8202P`, `8174P`, `8234L`, `8274L`, CASE_NO, COMPANY_NO, 라인번호 모두 미검출)
- 콘텐츠 진위: MUL_WGT 1,658 / DAY_CAPA 200 / 8.29×~9.03× / SCD000+10=11 모두 분석 보고서와 일치
- **CRITICAL/HIGH 이슈 없음**
- MEDIUM: slide 24 카테고리 명칭이 "기술2"로 분류됐지만 KPT+Pre-flight 콘텐츠 — eyebrow 명칭 보정 권고
- LOW: RES004 코드도 RES_X로 마스킹하면 안전 마진 확보

## 최종 산출물
- 발표자료: `Kshift_Workshop_Presentation.html`
- 결정 로그: `decisions.md` (이 파일)

## Status
COMPLETE — 2026-04-27

---

## 사용자 추가 요청 (2026-04-28)
1. HTML 로드 시 자동 전체화면 (F11 효과)
2. 라이트 테마 기본 (다크 텍스트 대비도 함께 강화)
3. 기본 150% 스케일
4. 표지: 발표자 박상훈 / 발표일 2026-04-29

### Implementer v2 적용 결과
- `<html lang="ko" class="light">` — 라이트 테마 기본 (FOUC 없음)
- `html { font-size: 24px; }` — 기본 150% 스케일 (root font-size 방식)
- `<div id="fs-prompt">` 안내 오버레이 + capture 단계 keydown/click 리스너로 첫 제스처 시 `requestFullscreen()` 호출 (브라우저 보안상 자동 호출 불가 → first-gesture 방식)
- F 키 = 전체화면 토글 / Z 키 = 100%↔150% 줌 토글 추가
- 다크 모드 텍스트 컨트라스트 강화: `--fg #f5f5f8` (AAA 13.6:1), `--fg-dim #b8b8c4`, `--fg-muted #8a92a2`
- slide 1 표지 + slide 25 Q&A 푸터: "발표자 박상훈" / "발표일 2026-04-29 (수)"

### Leader 자체 검증 (Grep)
- `<html class="light">` line 2 OK
- `font-size: 24px` line 27 OK
- `requestFullscreen` 함수 호출 line 2256~2260 OK
- "박상훈" / "2026-04-29" slide 1 (line 793~794) + slide 25 (line 2093) OK

## Status v2
COMPLETE — 2026-04-28
