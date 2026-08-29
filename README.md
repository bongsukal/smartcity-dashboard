# 스마트도시 지표 T점수 대시보드

전국 229개 시군구의 스마트도시 지표(원자료)를 구글시트에서 읽어 Z점수·T점수·백분위로 표준화하고,
분포 히스토그램·단계구분도(지도)·지역 진단으로 보여주는 Streamlit 대시보드입니다.

- 데이터 원천: 웹용 구글시트(링크가 있는 모든 사용자·뷰어). 앱은 CSV export URL로 무인증 읽기.
- 산식: Z = (원자료 − 평균) ÷ 표준편차(ddof=1) × 방향, T = 50 + 10Z, 백분위 = Z 평균순위 × 100 (지표별·비교집단 내)
- 시군구 경계: 2025-06-30 기준(SGIS 코드), 약 100 m 단순화 (`data/sgg_2025.geojson`)

## 로컬 실행

```
pip install -r requirements.txt
streamlit run app.py
```

시트 ID는 `.streamlit/secrets.toml`의 `SHEET_ID`가 있으면 그 값을, 없으면 `smartcity_core.py`의 `SHEET_ID` 상수를 사용합니다.

```toml
# .streamlit/secrets.toml (git에 올리지 않음)
SHEET_ID = "웹용 시트 ID"
```

## 배포 (Streamlit Community Cloud)

1. GitHub 공개 저장소에 아래 파일을 올린다:
   `app.py`, `smartcity_core.py`, `requirements.txt`, `README.md`, `.gitignore`,
   `.streamlit/config.toml`, `data/sgg_2025.geojson`, `data/sgg_code_table.csv`
2. https://share.streamlit.io → **New app** → 저장소·브랜치·`app.py` 선택
3. **Advanced settings → Secrets**에 `SHEET_ID = "웹용 시트 ID"` 입력 → Deploy
4. 이후 저장소에 push하면 자동 재배포된다. 시트 값 변경은 배포 없이 앱의 다음 읽기(캐시 10분) 또는
   [시트에서 새로 읽기] 버튼으로 반영된다.

## 시트 운영 규칙 요약

- 정본 시트(비공개)에서만 편집한다. Apps Script(`syncToWeb`, '변경 시' 트리거)가 두 탭의 값만 웹용 시트로 복사한다.
- 탭 구조: `지표정의`(1행 헤더, 6행부터 지표) / `가공된 지표정리_요약과 순서 일치`(1~4행 헤더, 5행부터 지역).
  **지표정의의 행 순서(6행부터) = 데이터 탭의 열 순서(E열부터)** — 행을 넣거나 빼면 데이터 탭의 열도 같은 위치에 넣거나 뺀다.
- `사용여부`가 "O"인 지표만 사용. 전 지역 결측 지표는 자동 제외되고, 값이 채워지면 자동 포함된다.
- 값 셀은 숫자만("X", "-", 문자는 결측 처리). 퍼센트는 `%` 기호 없이 숫자(예: 22.7)로 입력.
- 방향: `의미`에 "작을수록" 포함 → 낮을수록 좋은 지표로 계산. 같은 지표명이 여러 행이면 사용여부 O는 한 행만 둔다.
- 산식과 파싱 규칙(`smartcity_core.py`의 `load_definitions`/`load_values`/`add_tscore`)은 공용 코드이므로 수정하지 않는다.
