---

## 부록 A. Claude CLI Controller — WPF 연동 구현 보고서

### A.1 개요

기존 WPF 프로젝트에서 **Claude Code CLI**를 프로그래밍 방식으로 호출하여, AI의 로컬 소스 분석·파일 접근 기능을 활용한 뒤 응답을 WPF UI에 실시간 표시하는 연동 모듈을 구현하였다.

| 항목 | 내용 |
|------|------|
| **프로젝트명** | ClaudeCliController |
| **대상 프레임워크** | .NET 8.0 (WPF) |
| **인증 방식** | Claude Max 구독 OAuth (`claude login` 사전 인증) |
| **과금** | Max 구독료에 포함 (별도 API 크레딧 불필요) |
| **핵심 라이브러리** | CliWrap 3.6.7, CommunityToolkit.Mvvm 8.3.2 |
| **구현 파일 수** | 19개 (.cs 15개, .xaml 4개) |

### A.2 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│                     기존 WPF 프로젝트 (K-Viewer 등)               │
│                                                                   │
│  ┌─────────────────┐     ┌──────────────────────────────────┐    │
│  │   사용자 UI      │────▶│  ClaudeCliService                │    │
│  │  (분석 요청)     │     │  ┌──────────────────────────┐    │    │
│  │                  │     │  │ Cli.Wrap("claude")        │    │    │
│  │                  │     │  │  -p "프롬프트"            │    │    │
│  │                  │     │  │  --output-format          │    │    │
│  │                  │     │  │       stream-json         │    │    │
│  │                  │     │  │  --verbose                │    │    │
│  │                  │     │  │  --allowed-tools          │    │    │
│  │                  │     │  │       Read,Bash,Glob,Grep │    │    │
│  │                  │     │  └──────────┬───────────────┘    │    │
│  │                  │     │             │ stdout (NDJSON)     │    │
│  │                  │     │             ▼                     │    │
│  │                  │     │  ┌──────────────────────────┐    │    │
│  │                  │◀────│  │ ParseLine()              │    │    │
│  │  (실시간 표시)   │     │  │  → OnTextDelta (토큰)    │    │    │
│  │                  │     │  │  → OnResult (최종 결과)   │    │    │
│  │                  │     │  │  → OnToolUse (도구 실행)  │    │    │
│  └─────────────────┘     │  └──────────────────────────┘    │    │
│                           └──────────────────────────────────┘    │
│                                        │                          │
│                                        ▼                          │
│                              Claude Code CLI 프로세스              │
│                              (로컬 파일 접근 · 분석)               │
└──────────────────────────────────────────────────────────────────┘
```

### A.3 데이터 흐름

```
1. 사용자가 프롬프트 입력 (예: "src 폴더 구조를 분석해줘")
       │
2. MainViewModel.RunPrompt()
       │  ── 유저 메시지를 Messages에 추가
       │  ── 빈 Assistant 메시지 생성 (IsStreaming=true)
       │  ── CancellationTokenSource 생성
       ▼
3. ClaudeCliService.RunAsync(prompt, workingDir, sessionId, tools, ct)
       │
       │  CliWrap으로 프로세스 실행:
       │  claude -p "프롬프트" --output-format stream-json
       │         --verbose --include-partial-messages
       │         --allowed-tools Bash,Read,Glob,Grep
       ▼
4. Claude Code CLI (자식 프로세스)
       │  ── 로컬 파일시스템 접근 (Read, Glob, Grep 도구)
       │  ── Bash 명령 실행 (dotnet build, git log 등)
       │  ── stdout으로 NDJSON 스트리밍
       ▼
5. ParseLine() — 한 줄씩 JSON 파싱
       │
       ├── type: "system/init"   → OnSessionInit(sessionId, tools[])
       ├── type: "stream_event"  → OnTextDelta(토큰 문자열)  ← 실시간
       ├── type: "result"        → OnResult(결과, 비용, 턴수)
       └── type: "assistant"     → (verbose 모드에서 무시, 중복 방지)
       │
6. MainViewModel 이벤트 핸들러
       │  ── Dispatcher.Invoke로 UI 스레드 마샬링
       │  ── _currentAssistantMessage.AppendText(delta)
       │  ── 채팅 버블에 실시간 텍스트 추가
       ▼
7. 사용자에게 실시간 스트리밍 응답 표시
       │  ── 완료 시: Status=Done, 비용/턴수 업데이트
       │  ── session_id 저장 → 다음 호출 시 --resume으로 대화 이어가기
```

### A.4 핵심 구현 코드

#### A.4.1 Claude CLI 서비스 (CliWrap 기반)

```csharp
// Services/ClaudeCliService.cs — 핵심 실행 메서드

public async Task RunAsync(
    string prompt,
    string workingDirectory,
    string? sessionId = null,
    string allowedTools = "Bash,Edit,Read,Write,Glob,Grep",
    CancellationToken cancellationToken = default)
{
    var args = BuildArguments(prompt, sessionId, allowedTools);

    await Cli.Wrap(ClaudeExecutable)
        .WithArguments(args)                              // 배열 → 자동 이스케이프
        .WithWorkingDirectory(workingDirectory)            // 분석 대상 프로젝트 경로
        .WithStandardOutputPipe(
            PipeTarget.ToDelegate(ParseLine, Encoding.UTF8))  // 라인별 콜백
        .WithStandardErrorPipe(
            PipeTarget.ToDelegate(line => OnError?.Invoke(line), Encoding.UTF8))
        .WithValidation(CommandResultValidation.None)     // 비-0 종료 허용
        .ExecuteAsync(cancellationToken);
}

private string[] BuildArguments(string prompt, string? sessionId, string allowedTools)
{
    var args = new List<string>
    {
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--allowed-tools", allowedTools
    };

    if (!string.IsNullOrWhiteSpace(sessionId))
    {
        args.Add("--resume");
        args.Add(sessionId);
    }

    return args.ToArray();
}
```

#### A.4.2 stream-json 파싱

```csharp
// Services/ClaudeCliService.cs — 스트리밍 JSON 파싱

private void ParseLine(string line)
{
    if (string.IsNullOrWhiteSpace(line)) return;

    using var doc = JsonDocument.Parse(line);
    var root = doc.RootElement;
    var type = root.GetProperty("type").GetString();

    switch (type)
    {
        case "system":
            HandleSystemMessage(root);    // session_id, tools[] 추출
            break;
        case "stream_event":
            HandleStreamEvent(root);      // text_delta 토큰 추출
            break;
        case "result":
            HandleResultMessage(root);    // 최종 결과, 비용, 세션ID
            break;
        // "assistant" 타입은 verbose 모드에서 stream_event와 중복 → 무시
    }
}
```

**stream_event 텍스트 델타 추출:**

```csharp
private void HandleStreamEvent(JsonElement root)
{
    // stream_event → type == "content_block_delta" → delta.type == "text_delta"
    if (!root.TryGetProperty("stream_event", out var evt)) return;
    if (evt.GetProperty("type").GetString() != "content_block_delta") return;
    if (!evt.TryGetProperty("delta", out var delta)) return;
    if (delta.GetProperty("type").GetString() != "text_delta") return;

    var text = delta.GetProperty("text").GetString();
    if (!string.IsNullOrEmpty(text))
        OnTextDelta?.Invoke(text);   // → ViewModel → UI 실시간 표시
}
```

#### A.4.3 ViewModel 이벤트 처리 (UI 스레드 마샬링)

```csharp
// ViewModels/MainViewModel.cs — 스트리밍 응답 처리

private void HandleTextDelta(string delta)
{
    Application.Current.Dispatcher.Invoke(() =>
    {
        _currentAssistantMessage?.AppendText(delta);
    });
}

private void HandleResult(string? result, string? sessionId,
                           decimal costUsd, int numTurns, bool isError)
{
    Application.Current.Dispatcher.Invoke(() =>
    {
        _currentAssistantMessage?.Complete();
        _currentAssistantMessage = null;

        CurrentSessionId = sessionId;    // --resume 대화 이어가기용
        TotalCost += costUsd;
        TurnCount += numTurns;
        Status = isError ? AppStatus.Error : AppStatus.Done;
    });
}
```

#### A.4.4 기존 WPF 프로젝트에서 호출하는 예시

```csharp
// 기존 WPF 프로젝트에서 ClaudeCliService를 직접 사용하는 패턴

// 1. 서비스 인스턴스 생성
var claudeService = new ClaudeCliService();

// 2. 이벤트 구독
claudeService.OnTextDelta += token =>
{
    Dispatcher.Invoke(() => resultTextBox.AppendText(token));
};

claudeService.OnResult += (result, sessionId, cost, turns, isError) =>
{
    Dispatcher.Invoke(() =>
    {
        statusLabel.Content = isError ? "오류 발생" : $"완료 (${cost:F4}, {turns}턴)";
        _lastSessionId = sessionId;  // 멀티턴 대화용 세션 ID 보관
    });
};

claudeService.OnError += error =>
{
    Dispatcher.Invoke(() => statusLabel.Content = $"에러: {error}");
};

// 3. 실행 (분석 대상 프로젝트 경로를 WorkingDirectory로 지정)
await claudeService.RunAsync(
    prompt: "이 프로젝트의 LP 모델 제약 조건을 분석해줘",
    workingDirectory: @"C:\Projects\TargetProject",
    sessionId: _lastSessionId,           // null이면 새 세션, 값이면 이어가기
    allowedTools: "Read,Glob,Grep,Bash",  // 읽기 전용 도구만 허용
    cancellationToken: _cts.Token
);
```

### A.5 stream-json 메시지 포맷

Claude CLI가 `--output-format stream-json --verbose` 옵션으로 stdout에 출력하는 NDJSON(Newline-Delimited JSON) 스트림의 메시지 타입별 구조:

| 순서 | type | 설명 | 주요 필드 |
|------|------|------|-----------|
| 1 | `system` (subtype: `init`) | 세션 초기화 | `session_id`, `tools[]` |
| 2 | `user` | 프롬프트 에코 | `message.content` |
| 3 | `stream_event` | 토큰 단위 스트리밍 | `stream_event.delta.text` |
| 4 | `assistant` | 완성된 응답 턴 | `message.content[].text` |
| 5 | `result` | 최종 결과 | `result`, `session_id`, `cost_usd`, `num_turns`, `is_error` |

**`stream_event` 텍스트 추출 경로:**
```
root.stream_event.type == "content_block_delta"
  → root.stream_event.delta.type == "text_delta"
    → root.stream_event.delta.text   ← 실시간 토큰
```

### A.6 프로젝트 구조

```
D:\Temp\ClaudeCliController\
├── ClaudeCliController.sln
└── ClaudeCliController\
    ├── ClaudeCliController.csproj
    ├── App.xaml / App.xaml.cs
    │
    ├── Models\
    │   ├── ChatMessage.cs          ← MessageRole(User/Assistant/System) + record
    │   ├── StreamJsonModels.cs     ← stream-json 파싱용 DTO 정의
    │   └── SessionInfo.cs          ← 세션 메타 정보
    │
    ├── Services\
    │   ├── ClaudeCliService.cs     ← ★ 핵심: CliWrap + stream-json 파싱
    │   ├── LogService.cs           ← 대화 로그 파일 저장
    │   └── SettingsService.cs      ← 앱 설정 JSON 직렬화
    │
    ├── ViewModels\
    │   ├── MainViewModel.cs        ← MVVM 커맨드 + 상태 관리
    │   ├── ChatMessageViewModel.cs ← 실시간 AppendText 스트리밍
    │   └── ToolItem.cs             ← 도구 체크박스 바인딩
    │
    ├── Views\
    │   ├── MainWindow.xaml         ← 다크 테마 채팅 UI
    │   ├── MainWindow.xaml.cs      ← Enter/Shift+Enter, 자동 스크롤
    │   └── Converters\             ← 4개 (Role→정렬, Role→색상, Bool→Visibility, Status→색상)
    │
    └── Themes\
        └── DarkTheme.xaml          ← 모던 다크 테마 리소스 딕셔너리
```

### A.7 NuGet 패키지 의존성

| 패키지 | 버전 | 용도 |
|--------|------|------|
| **CliWrap** | 3.6.7 | CLI 프로세스 관리, 라인별 stdout 콜백, CancellationToken 지원 |
| **CommunityToolkit.Mvvm** | 8.3.2 | Source Generator MVVM (`[ObservableProperty]`, `[RelayCommand]`) |
| **System.Text.Json** | (내장) | stream-json NDJSON 파싱 |

### A.8 인증 및 과금

```
┌─────────────────────┬──────────────────────┬─────────────────┐
│ 인증 방식           │ 과금                 │ 설정 방법       │
├─────────────────────┼──────────────────────┼─────────────────┤
│ OAuth (브라우저)    │ Max 구독 ($100/200)  │ claude login    │
├─────────────────────┼──────────────────────┼─────────────────┤
│ ANTHROPIC_API_KEY   │ API 크레딧 (종량제)  │ 환경변수 설정   │
└─────────────────────┴──────────────────────┴─────────────────┘
```

- 본 구현은 **OAuth 방식**을 사용하여 Max 구독 요금에 포함됨
- `--bare` 플래그를 사용하지 않으므로 로컬 OAuth 토큰을 자동으로 활용
- 사전 조건: 터미널에서 `claude login` 실행하여 브라우저 인증 완료 필요

### A.9 주요 CLI 플래그 참조

| 플래그 | 용도 | 본 구현 사용 여부 |
|--------|------|:-:|
| `-p "prompt"` | 비대화형 실행 | ✅ |
| `--output-format stream-json` | 실시간 NDJSON 스트리밍 | ✅ |
| `--verbose` | 턴별 상세 출력 | ✅ |
| `--include-partial-messages` | 토큰 단위 스트리밍 이벤트 | ✅ |
| `--allowed-tools "Read,Bash,..."` | 도구 사전 허용 | ✅ |
| `--resume <session-id>` | 세션 이어가기 | ✅ |
| `--max-turns N` | 에이전틱 턴 제한 | 선택적 |
| `--max-budget-usd N` | 비용 한도 | 선택적 |
| `--json-schema '{...}'` | 구조화 출력 스키마 강제 | 선택적 |
| `--bare` | 로컬 설정 스킵 (API key 필요) | ❌ (OAuth) |

### A.10 빌드 및 실행

```bash
# 사전 조건
npm install -g @anthropic-ai/claude-code   # Claude CLI 설치
claude login                                 # OAuth 인증 (1회)

# 빌드 및 실행
cd D:\Temp\ClaudeCliController
dotnet build
dotnet run
```
