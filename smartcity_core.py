"""
smartcity_core.py — 구글시트 → 원자료·Z점수·T점수·백분위 긴 테이블
스마트시티.ipynb(공용 코드)의 load_definitions / load_values / add_tscore 를 그대로 둔 것.
바뀐 부분은 시트를 읽는 방법뿐: Colab 인증 + gspread 대신, '링크가 있는 모든 사용자(뷰어)' 시트를
CSV export URL로 읽어 get_all_values()와 같은 문자열 2차원 배열을 돌려준다.
"""
import io
import urllib.parse
import urllib.request
import pandas as pd
import numpy as np

SHEET_ID = "1Zy0IrJmMXJ8DFnBBQiSGWP22bc1q4YMvR61I7pwwt3Q"   # 앱이 읽는 '웹용 시트' ID
DEF_SHEET = "지표정의"
DATA_SHEET = "가공된 지표정리_요약과 순서 일치"
GIDS = {DEF_SHEET: None, DATA_SHEET: None}   # 탭 고유번호(URL의 #gid=)를 알면 적는다. None이면 탭 이름으로 읽음


# ── 시트 읽기 (노트북의 sh.worksheet(name).get_all_values() 를 대체) ──────────
def fetch_grid(sheet_id, sheet_name=None, gid=None):
    """인증 없이 CSV로 받아 gspread get_all_values()와 같은 형태(문자열 2차원 배열)로 반환"""
    base = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    if gid is not None:
        url = f"{base}/export?format=csv&gid={gid}"                       # 원본 격자 그대로
    else:
        url = f"{base}/gviz/tq?tqx=out:csv&headers=1&sheet={urllib.parse.quote(sheet_name)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=60).read()
    df = pd.read_csv(io.BytesIO(raw), header=None, dtype=str, keep_default_na=False)
    return df.values.tolist()


def get_all_values(sheet_name):
    return fetch_grid(SHEET_ID, sheet_name, GIDS.get(sheet_name))


# ── 이하 세 함수는 스마트시티.ipynb 와 동일 (raw 인자만 선택 사항으로 추가: 시트 없이 검증용) ──
def load_definitions(raw=None):
    if raw is None:
        raw = get_all_values(DEF_SHEET)
    df = pd.DataFrame(raw[1:], columns=raw[0])   # 1행 헤더를 그대로 사용
    df.columns = [c.strip() for c in df.columns]
    print("정의시트 컬럼:", list(df.columns))     # 실제 이름 확인용

    df = df.iloc[4:].reset_index(drop=True)      # 5번째 행부터 실제 지표
    df["col_idx"] = df.index + 4                 # 데이터시트 E열 = 인덱스 4
    df = df[df["지표명"].str.strip() != ""]

    df["방향"] = np.where(df["의미"].str.contains("작을수록", na=False), -1, 1)
    df["유형"] = np.select(
        [df["의미"].str.contains("1은 있음", na=False),
         df["의미"].str.contains("독자시스템", na=False)],
        ["binary", "ordinal"], default="continuous")
    return df


def load_values(defs, raw=None):
    if raw is None:
        raw = get_all_values(DATA_SHEET)
    data = pd.DataFrame(raw[4:])                 # 5행부터 값
    use = defs[defs["사용여부"] == "O"]

    cols = [0, 1, 2, 3] + list(use["col_idx"])
    df = data.iloc[:, cols].copy()
    df.columns = ["시도명", "시군구명", "지역", "인구규모"] + list(use["지표명"])
    df = df[df["지역"].str.strip() != ""]

    long = df.melt(id_vars=["시도명", "시군구명", "지역", "인구규모"],
                   var_name="지표명", value_name="원자료")
    long["원자료"] = pd.to_numeric(
        long["원자료"].astype(str).str.replace(",", "").str.strip(),
        errors="coerce")
    # 전 지역 결측인 지표만 제외
    valid = long.groupby("지표명")["원자료"].transform("count") > 0
    long = long[valid]
    return long.merge(use[["지표명", "대분류", "데이터유형", "의미", "방향", "유형"]],
                      on="지표명", how="left")


def add_tscore(long, group_col=None):
    """group_col=None이면 전국, '시도명' 등을 주면 그 안에서 표준화"""
    keys = ["지표명"] + ([group_col] if group_col else [])
    g = long.groupby(keys)["원자료"]
    mean, std = g.transform("mean"), g.transform("std")

    z = (long["원자료"] - mean) / std.replace(0, np.nan)
    long["Z점수"] = z * long["방향"]
    long["T점수"] = 50 + 10 * long["Z점수"]
    long["백분위"] = long.groupby(keys)["Z점수"].rank(pct=True) * 100
    return long


OUT_COLS = ["시도명", "시군구명", "지역", "인구규모", "대분류", "지표명",
            "데이터유형", "의미", "방향", "유형",
            "원자료", "Z점수", "T점수", "백분위"]


def build_table(sheet_id=SHEET_ID, group_col=None):
    """앱용 진입점: 시트 → smartcity_data.csv 와 같은 형식의 DataFrame (노트북 셀 1~3을 한 번에)"""
    defs = load_definitions(fetch_grid(sheet_id, DEF_SHEET, GIDS.get(DEF_SHEET)))
    long = add_tscore(load_values(defs, fetch_grid(sheet_id, DATA_SHEET, GIDS.get(DATA_SHEET))), group_col)
    return long[OUT_COLS].reset_index(drop=True)


if __name__ == "__main__":
    # 노트북 셀 1~3과 같은 흐름
    defs = load_definitions()
    long = add_tscore(load_values(defs))

    print(f"지표 {long['지표명'].nunique()}개 / 지역 {long['지역'].nunique()}곳")
    print(long["유형"].value_counts())
    print("\n결측 상위:")
    print(long[long["원자료"].isna()].groupby("지표명").size().sort_values(ascending=False).head(10))

    out = long[OUT_COLS]
    out.to_csv("smartcity_table.csv", index=False, encoding="utf-8-sig")   # 기준 파일과 이름을 달리해 덮어쓰기 방지
    print(f"{len(out):,}행 / {out['지표명'].nunique()}개 지표 / {out['지역'].nunique()}곳 → smartcity_table.csv")
