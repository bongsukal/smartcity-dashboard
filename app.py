# app.py — 스마트도시 지표 T점수 대시보드
# 구성은 참고 앱(smartcities-knu)을 따름: 상단 필터 → 요약 통계 → 분포|공간분포 → 지역 진단 → 세부지표.
# core는 build_table()만 호출한다. 산식·파싱은 smartcity_core.py(공용 코드)에 있고 여기서 손대지 않는다.
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import smartcity_core as core

st.set_page_config(page_title="스마트도시 서비스 수준 대시보드", layout="wide")

SHEET_NAME = "스마트도시_웹용 (구글시트)"
FORMULA_NOTE = ("산식: Z = (원자료 − 평균) ÷ 표준편차(ddof=1) × 방향, "
                "T = 50 + 10Z, 백분위 = Z 평균순위 × 100 (지표별·비교집단 내)")
MAP_NOTE = "시군구 경계: 2025-06-30 기준(SGIS 코드)"
GEOJSON_PATH = Path(__file__).parent / "data" / "sgg_korea.geojson"
LIGHT_BAR, DARK_BAR = "#9ecae1", "#1c5ba6"     # 진단 막대(50 미만/이상)
MISS_GRAY = "#d9d9d9"                           # 지도 결측
BORDER_GRAY = "#999999"                         # 지도 경계선
NONE_SGG = "전체"
NUMFMT = {
    "Z점수": st.column_config.NumberColumn(format="%.2f"),
    "T점수": st.column_config.NumberColumn(format="%.1f"),
    "백분위": st.column_config.NumberColumn(format="%.1f"),
}


def get_sheet_id():
    try:
        if "SHEET_ID" in st.secrets:
            return st.secrets["SHEET_ID"]
    except Exception:
        pass
    return core.SHEET_ID


@st.cache_data(ttl=600, show_spinner="구글시트에서 데이터를 읽는 중...")
def fetch(sheet_id, group_col):
    return core.build_table(sheet_id=sheet_id, group_col=group_col), datetime.now()


def load(sheet_id, group_col):
    """읽기 실패 시 마지막 정상 데이터 유지. 반환: (df, 읽은 시각, 오류 or None)"""
    key = f"last_good_{group_col or '전국'}"
    try:
        df, ts = fetch(sheet_id, group_col)
        st.session_state[key] = (df, ts)
        return df, ts, None
    except Exception as e:
        if key in st.session_state:
            df, ts = st.session_state[key]
            return df, ts, e
        return None, None, e


@st.cache_data(show_spinner=False)
def load_geojson():
    gj = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
    return gj, {f["properties"]["지역"].strip() for f in gj["features"]}


sheet_id = get_sheet_id()
base, base_ts, base_err = load(sheet_id, None)          # 전국 기준(필터 목록·기본 화면)
if base is None:
    st.error(f"시트 읽기 실패({datetime.now():%Y-%m-%d %H:%M:%S}) — 표시할 데이터가 없습니다. 사유: {base_err}")
    st.stop()

# ── 상단: 제목 · 기준 시각 · 새로 읽기 ──────────────────────────
head_l, head_r = st.columns([5, 1])
with head_l:
    st.title("스마트도시 서비스 수준 대시보드")
    ts_slot = st.empty()
with head_r:
    if st.button("🔄 시트에서 새로 읽기", use_container_width=True):
        fetch.clear()
        st.rerun()

# ── 필터 (상단 2행) ──────────────────────────────────────────
f1, f2, f3 = st.columns([1.2, 2, 1])
with f1:
    sel_cat = st.selectbox("대분류", ["전체"] + list(pd.unique(base["대분류"])))
with f2:
    ind_pool = base if sel_cat == "전체" else base[base["대분류"] == sel_cat]
    sel_ind = st.selectbox("지표", list(pd.unique(ind_pool["지표명"])))
with f3:
    basis = st.radio("값 기준", ["T점수", "원자료"], horizontal=True)

g1, g2, g3 = st.columns([1.2, 2, 1])
with g1:
    sel_sido = st.selectbox("시도", ["전체"] + sorted(base["시도명"].unique()))
with g2:
    sgg_opts = [NONE_SGG] + (sorted(base.loc[base["시도명"] == sel_sido, "시군구명"].unique())
                             if sel_sido != "전체" else [])
    sel_sgg = st.selectbox("시군구", sgg_opts, disabled=(sel_sido == "전체"))
with g3:
    group_label = st.selectbox("비교집단", ["전국", "시도 내"],
                               help="시도 내: 같은 시도 안에서 평균·표준편차를 구해 표준화")

region = None
if sel_sido != "전체" and sel_sgg != NONE_SGG:
    region = base.loc[(base["시도명"] == sel_sido) & (base["시군구명"] == sel_sgg), "지역"].iloc[0]

if group_label == "시도 내":
    df, ts, err = load(sheet_id, "시도명")
    if df is None:
        st.error(f"시트 읽기 실패({datetime.now():%Y-%m-%d %H:%M:%S}) — 표시할 데이터가 없습니다. 사유: {err}")
        st.stop()
else:
    df, ts, err = base, base_ts, base_err

ts_slot.caption(f"데이터 기준 시각(마지막 성공 읽기): {ts:%Y-%m-%d %H:%M:%S} · 원천: {SHEET_NAME}")
if err is not None:
    st.warning(f"시트 읽기 실패({datetime.now():%Y-%m-%d %H:%M:%S}) — "
               f"마지막 정상 데이터({ts:%Y-%m-%d %H:%M:%S})를 표시 중입니다. 사유: {err}")

# ── 선택 지표 데이터 (229개 지역 전체 — 시도 선택은 진단·강조에만 쓰인다) ──
ind_df = df[df["지표명"] == sel_ind].copy()
ind_df["지역"] = ind_df["지역"].str.strip()
vals = ind_df[basis].dropna()
st.caption(f"비교집단: {group_label} · 유효 지역 {vals.count()}곳 / 전체 {len(ind_df)}곳 · 지표: {sel_ind}")

# ── 요약 통계 ────────────────────────────────────────────────
if vals.empty:
    st.info("이 지표는 현재 값 기준으로 표시할 값이 없습니다(전부 결측).")
    st.stop()
fmt = (lambda v: f"{v:,.1f}") if basis == "T점수" else (lambda v: f"{v:,.4g}")
for col, (label, v) in zip(st.columns(5), [
        ("최소", vals.min()), ("25%", vals.quantile(.25)), ("중앙값", vals.median()),
        ("75%", vals.quantile(.75)), ("평균", vals.mean())]):
    col.metric(label, fmt(v))

clip = None
if basis == "T점수":
    clip = st.slider("극단값 묶기 기준 (T점수) — 표시용, 계산값은 바뀌지 않음", 55, 80, 60)

# 순위(마우스 오버·진단용): 비교집단 안에서 T점수 내림차순
if group_label == "시도 내":
    rank = ind_df.groupby("시도명")["T점수"].rank(ascending=False, method="min")
    n_valid = ind_df.groupby("시도명")["T점수"].transform("count")
else:
    rank = ind_df["T점수"].rank(ascending=False, method="min")
    n_valid = pd.Series(ind_df["T점수"].count(), index=ind_df.index)
ind_df["순위표시"] = [f"{int(r)} / {int(n)}" if pd.notna(r) else "—" for r, n in zip(rank, n_valid)]

# ── 분포 | 공간분포 ──────────────────────────────────────────
c_hist, c_map = st.columns(2)

with c_hist:
    st.subheader("전국 분포")
    x = ind_df[basis].dropna()
    lo = hi = None
    if clip is not None:
        lo, hi = 100 - clip, clip
        n_lo, n_hi = int((x < lo).sum()), int((x > hi).sum())
        x = x.clip(lo, hi)
    fig = px.histogram(x=x, nbins=40)
    fig.update_traces(marker_color=LIGHT_BAR, marker_line_color="white", marker_line_width=0.5)
    center = 50 if basis == "T점수" else x.mean()
    fig.add_vline(x=center, line_dash="dash", line_color="gray",
                  annotation_text=f"평균 {center:.0f}" if basis == "T점수" else "평균")
    if clip is not None:
        if n_hi:
            fig.add_annotation(x=hi, yref="paper", y=1.06, showarrow=False, text=f"{hi}+ {n_hi}곳")
        if n_lo:
            fig.add_annotation(x=lo, yref="paper", y=1.06, showarrow=False, text=f"{lo}− {n_lo}곳")
    if region is not None:
        r_val = ind_df.loc[ind_df["지역"] == region, basis].iloc[0]
        if pd.notna(r_val):
            r_show = min(max(r_val, lo), hi) if clip is not None else r_val
            fig.add_vline(x=r_show, line_color="#14324f", line_width=2)
            fig.add_annotation(x=r_show, yref="paper", y=1.14, showarrow=False,
                               text=sel_sgg, font=dict(color="#14324f"))
        else:
            st.caption(f"※ {region}은(는) 현재 값 기준({basis})이 결측입니다.")
    fig.update_layout(height=430, xaxis_title=basis, yaxis_title="지역 수",
                      showlegend=False, margin=dict(t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)

with c_map:
    st.subheader("전국 공간분포")
    gj, gj_names = load_geojson()
    unmatched = sorted(set(ind_df["지역"]) - gj_names)
    if unmatched:
        st.warning(f"지도에 조인되지 않는 시군구 {len(unmatched)}개: {', '.join(unmatched)}")
    present = ind_df[ind_df[basis].notna()].copy()
    missing = ind_df[ind_df[basis].isna()]
    present["T표시"] = present["T점수"].map(lambda t: f"{t:.1f}" if pd.notna(t) else "—")
    present["상위표시"] = present["백분위"].map(
        lambda p: f"상위 {100 - p:.0f}%" if pd.notna(p) else "—")
    is_binary = ind_df["유형"].iloc[0] == "binary"      # 여부형 지표: 흰색 → 옅은 초록 2색
    scale = [[0, "#ffffff"], [1, "#74c476"]] if is_binary else "Greens"
    if basis == "T점수":
        rng = (100 - clip, clip)
    elif is_binary:
        rng = (0, 1)
    else:
        rng = (vals.quantile(.05), vals.quantile(.95))
        if rng[0] == rng[1]:
            rng = (vals.min(), max(vals.max(), vals.min() + 1))
    mfig = px.choropleth(present, geojson=gj, locations="지역", featureidkey="properties.지역",
                         color=basis, color_continuous_scale=scale, range_color=rng,
                         custom_data=["지역", "원자료", "T표시", "상위표시", "순위표시"])
    mfig.update_traces(marker_line_color=BORDER_GRAY, marker_line_width=0.4,
                       hovertemplate="%{customdata[0]}<br>원자료 %{customdata[1]}"
                                     "<br>T점수 %{customdata[2]} · %{customdata[3]}"
                                     "<br>순위 %{customdata[4]}<extra></extra>")
    if not missing.empty:
        mfig.add_trace(go.Choropleth(
            geojson=gj, locations=missing["지역"], featureidkey="properties.지역",
            z=[0] * len(missing), colorscale=[[0, MISS_GRAY], [1, MISS_GRAY]], showscale=False,
            marker_line_color=BORDER_GRAY, marker_line_width=0.4,
            hovertemplate="%{location}<br>결측<extra></extra>"))
    if region is not None:
        mfig.add_trace(go.Choropleth(
            geojson=gj, locations=[region], featureidkey="properties.지역",
            z=[0], colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
            marker_line_color="crimson", marker_line_width=2.5, hoverinfo="skip"))
    mfig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
    mfig.update_layout(height=430, margin=dict(t=10, b=10, l=0, r=0),
                       coloraxis_colorbar=dict(title=basis))
    st.plotly_chart(mfig, use_container_width=True)
    st.caption(MAP_NOTE)

# ── 지역 진단 ────────────────────────────────────────────────
if region is None:
    st.info("시도와 시군구를 선택하면 지역별 진단이 표시됩니다.")
else:
    st.subheader(f"{region} 진단")
    scope = df if group_label == "전국" else df[df["시도명"] == sel_sido]
    # 위치 = 대분류 지표들의 백분위 평균 (참고 앱과 같은 방식: 상위 X% = 100 − 백분위평균, 33% 컷)
    mine = (scope[scope["지역"] == region]
            .groupby("대분류", sort=False)
            .agg(T점수=("T점수", "mean"), 백분위평균=("백분위", "mean"), 지표수=("지표명", "size"))
            .reset_index())

    def pos_label(r):
        if pd.isna(r["백분위평균"]):
            return "—"
        top = 100 - r["백분위평균"]
        if top <= 33:
            return f"상위 {top:.0f}%"
        if r["백분위평균"] <= 33:
            return f"하위 {r['백분위평균']:.0f}%"
        return "중간"

    pos_col = "전국 내 위치" if group_label == "전국" else "시도 내 위치"
    mine[pos_col] = mine.apply(pos_label, axis=1)

    order = st.radio("정렬", ["높은 값 순", "낮은 값 순"], horizontal=True,
                     label_visibility="collapsed")
    bar_df = mine.dropna(subset=["T점수"]).sort_values(
        "T점수", ascending=(order == "낮은 값 순"))
    bfig = go.Figure(go.Bar(
        x=bar_df["T점수"], y=bar_df["대분류"], orientation="h",
        text=[f"{v:.0f}" for v in bar_df["T점수"]], textposition="outside",
        marker_color=[LIGHT_BAR if v < 50 else DARK_BAR for v in bar_df["T점수"]]))
    bfig.add_vline(x=50, line_dash="dash", line_color="gray")
    bfig.update_layout(height=max(300, 34 * len(bar_df) + 60), xaxis_title="T점수",
                       yaxis_title=None, margin=dict(t=20, b=10), showlegend=False)
    st.plotly_chart(bfig, use_container_width=True)

    st.dataframe(
        mine.rename(columns={"대분류": "항목"})[["항목", "T점수", pos_col, "지표수"]],
        column_config=NUMFMT, hide_index=True, use_container_width=True)

    with st.expander("지표별 상세 보기"):
        det = scope.copy()
        det["순위"] = det.groupby("지표명")["T점수"].rank(ascending=False, method="min")
        det["유효"] = det.groupby("지표명")["T점수"].transform("count")
        det = det[det["지역"] == region].copy()
        det["순위/유효지역수"] = det.apply(
            lambda r: f"{int(r['순위'])} / {int(r['유효'])}" if pd.notna(r["순위"]) else "—", axis=1)
        st.dataframe(det[["대분류", "지표명", "원자료", "T점수", "백분위", "순위/유효지역수"]],
                     column_config=NUMFMT, hide_index=True, use_container_width=True)

# ── 세부지표 전체 보기 ───────────────────────────────────────
st.divider()
with st.expander("세부지표 전체 보기"):
    st.caption(f"전체 {df['지역'].nunique()}개 지역 × {df['지표명'].nunique()}개 지표 · 값 기준 {basis}")
    wide = (df.pivot_table(index=["시도명", "시군구명"], columns="지표명",
                           values=basis, aggfunc="first", sort=False)
            .reindex(columns=pd.unique(df["지표명"])).reset_index())
    if basis == "T점수":
        wide = wide.round(1)
    st.dataframe(wide, hide_index=True, use_container_width=True)
    src_line = (f"# 출처: {SHEET_NAME} · 읽은 시각 {ts:%Y-%m-%d %H:%M:%S} · "
                f"비교집단 {group_label} · {FORMULA_NOTE}\n")
    csv_bytes = (src_line + df[core.OUT_COLS].to_csv(index=False)).encode("utf-8-sig")
    st.download_button(
        "CSV 내려받기", csv_bytes,
        file_name=f"smartcity_table_{'전국' if group_label == '전국' else '시도내'}.csv",
        mime="text/csv",
        help="현재 비교집단 기준의 전체 지표×지역 긴 테이블(utf-8-sig). 첫 줄은 # 출처 주석입니다.")

# ── 하단 출처 ────────────────────────────────────────────────
st.divider()
st.caption(f"출처: {SHEET_NAME} · 읽은 시각 {ts:%Y-%m-%d %H:%M:%S} · {FORMULA_NOTE} · {MAP_NOTE}")
