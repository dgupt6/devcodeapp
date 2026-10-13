# Agent driven T-Mobile bill analyzer (Streamlit).
# An LLM agent (Ollama local / free cloud tier / Anthropic fallback) reads the
# "THIS BILL SUMMARY" table from the bill PDF -- no regex parsing. The per line
# math, CSV download and email are reused unchanged from webreadBillpdf.py.
# Developer :  Devraj Gupta
# Version 1.0 Sep 2026
#
# In terminal do : streamlit run agentTmobileBillApp.py
# CTRL-C to stop the app in terminal (mac os)
#
# Setup:
#   pip install streamlit pdfplumber pandas pydantic requests openai anthropic
#   Default provider: Groq free tier -- put GROQ_API_KEY in .streamlit/secrets.toml
#   Other keys (sidebar, st.secrets or env): GEMINI_API_KEY, OPENROUTER_API_KEY,
#   ANTHROPIC_API_KEY. Local/free alternative: Ollama (`ollama pull qwen2.5:7b`)
########################################################################
import io
import json
import os

import pandas as pd
import streamlit as st

from webreadBillpdf import deriveActualAmt, validateAndSend
from tmobile_bill_agent.llm_providers import PROVIDERS, LLMClient, LLMError, list_ollama_models
from tmobile_bill_agent.extraction_agent import (
    run_bill_agent, validate_table, to_derive_frame, balance_cents)

AMOUNT_COLS = ["Plans", "Equipment", "Services", "One-time", "Total"]


def default_api_key(env_name):
    if not env_name:
        return ""
    try:
        if env_name in st.secrets:
            return st.secrets[env_name]
    except Exception:
        pass  # no secrets.toml
    return os.environ.get(env_name, "")


def ensure_email_config():
    """webreadBillpdf.load_email_list() reads config.json. That file is not committed to git,
    so on Streamlit Cloud build it from the to_address_list / main_address_list secrets."""
    if os.path.exists("config.json"):
        return True
    try:
        lists = {k: list(st.secrets[k]) for k in ("to_address_list", "main_address_list")}
    except Exception:
        return False
    with open("config.json", "w") as file:
        json.dump(lists, file)
    return True


def llm_sidebar():
    with st.sidebar:
        st.title("LLM settings")
        provider = st.selectbox("Provider", list(PROVIDERS), index=0)
        cfg = PROVIDERS[provider]
        st.caption(cfg["help"])

        if cfg["kind"] == "ollama":
            models = list_ollama_models()
            if models:
                default = cfg["default_model"] if cfg["default_model"] in models else models[0]
                model = st.selectbox("Model", models, index=models.index(default))
            else:
                st.warning("Ollama not reachable or no models pulled. Run `ollama serve` "
                           "and `ollama pull qwen2.5:7b`.")
                model = st.text_input("Model", cfg["default_model"])
            api_key = None
        else:
            model = st.text_input("Model", cfg["default_model"])
            api_key = st.text_input(f"API key ({cfg['key_env']})", type="password",
                                    value=default_api_key(cfg["key_env"]),
                                    help="Kept only in this browser session; never saved to disk.")

        max_attempts = st.slider("Max agent attempts", 1, 5, 3)

        if st.button("Test connection"):
            try:
                ok = LLMClient(provider, model, api_key).test_connection()
                if ok:
                    st.success("Connected ✓")
                else:
                    st.warning("Connected, but unexpected reply.")
            except LLMError as exc:
                st.error(str(exc))
        st.divider()
    return provider, model, api_key, max_attempts


def run_agent(pdf_bytes, provider, model, api_key, max_attempts):
    try:
        llm = LLMClient(provider, model, api_key)
    except LLMError as exc:
        st.error(str(exc))
        return None
    with st.status("Agent is reading the bill...", expanded=True) as status:
        try:
            result = run_bill_agent(io.BytesIO(pdf_bytes), llm, max_attempts=max_attempts,
                                    on_step=st.write)
        except LLMError as exc:
            status.update(label="Agent failed", state="error")
            st.error(str(exc))
            return None
        if result.ok:
            status.update(label=f"Extraction validated in {result.attempts} attempt(s) ✓",
                          state="complete", expanded=False)
        else:
            status.update(label="Extraction has issues -- please review/edit the table below",
                          state="error", expanded=True)
    return result


def adjustment_editor(calculated, statement_total):
    """Per person amounts: editable 'Final amount', plus auto-balance of the cents gap."""
    signature = tuple(calculated.items())
    if st.session_state.get("adj_signature") != signature:
        st.session_state.adj_signature = signature
        st.session_state.adj_base = dict(calculated)
        st.session_state.adj_version = st.session_state.get("adj_version", 0) + 1

    col1, col2, _ = st.columns([1, 1, 2])
    if col1.button("Auto-balance cents", help="Spread the difference to the bill total one cent "
                                              "at a time, largest amounts first."):
        st.session_state.adj_base = balance_cents(calculated, statement_total)
        st.session_state.adj_version += 1
    if col2.button("Reset adjustments"):
        st.session_state.adj_base = dict(calculated)
        st.session_state.adj_version += 1

    base_df = pd.DataFrame({
        "Person": list(calculated),
        "Calculated amount": list(calculated.values()),
        "Final amount": [st.session_state.adj_base.get(p, calculated[p]) for p in calculated],
    })
    edited = st.data_editor(
        base_df,
        key=f"adj_editor_{st.session_state.adj_version}",
        hide_index=True,
        disabled=["Person", "Calculated amount"],
        column_config={
            "Calculated amount": st.column_config.NumberColumn(format="$%.2f"),
            "Final amount": st.column_config.NumberColumn(format="$%.2f", step=0.01, min_value=0.0),
        },
        use_container_width=True,
    )
    edited["Adjustment"] = (edited["Final amount"] - edited["Calculated amount"]).round(2)
    adjusted = edited[edited["Adjustment"] != 0]
    if not adjusted.empty:
        st.caption("Adjustments: " + ", ".join(
            f"{r.Person} {r.Adjustment:+.2f}" for r in adjusted.itertuples()))
    return pd.DataFrame({"Person": edited["Person"],
                         "Individual amount": edited["Final amount"].round(2)})


if __name__ == "__main__":
    st.set_page_config(page_title="Agent T-Mobile Bill Analyzer", layout="wide")
    st.title("🤖 Agent T-Mobile Bill Analyzer ( Devraj Gupta )")
    provider, model, api_key, max_attempts = llm_sidebar()

    st.write("Upload the T-mobile bill file; an LLM agent extracts the per line charges.")
    uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])
    if not uploaded_file:
        st.session_state.pop("extraction", None)
        st.stop()

    file_key = (uploaded_file.name, uploaded_file.size)
    extraction = st.session_state.get("extraction")
    if extraction and extraction["file_key"] != file_key:
        st.session_state.pop("extraction", None)
        extraction = None

    if st.button("Run extraction agent" if not extraction else "Re-run extraction agent",
                 type="primary"):
        result = run_agent(uploaded_file.getvalue(), provider, model, api_key, max_attempts)
        if result is not None and result.df is not None:
            extraction = {"file_key": file_key, "df": result.df,
                          "total": result.statement_total, "steps": result.steps,
                          "model": f"{provider} / {model}"}
            st.session_state.extraction = extraction
            st.session_state.extract_version = st.session_state.get("extract_version", 0) + 1

    if not extraction:
        st.stop()

    # ---- 1. Extracted bill lines (editable, re-validated live)
    st.subheader("1. Extracted bill summary")
    st.caption(f"Extracted by {extraction['model']}. Edit any cell if the agent misread it.")
    with st.expander("Agent log"):
        for step in extraction["steps"]:
            st.write(step)
    bill_df = st.data_editor(
        extraction["df"],
        key=f"bill_editor_{st.session_state.extract_version}",
        hide_index=True,
        num_rows="dynamic",
        column_config={c: st.column_config.NumberColumn(format="$%.2f", step=0.01)
                       for c in AMOUNT_COLS},
        use_container_width=True,
    )
    bill_df[AMOUNT_COLS] = bill_df[AMOUNT_COLS].fillna(0.0).astype(float)
    bill_df = bill_df.dropna(subset=["Phone Number"])
    totalBill = st.number_input("Total bill statement amount", value=float(extraction["total"]),
                                step=0.01, format="%.2f")

    issues = validate_table(bill_df, totalBill)
    if issues:
        st.warning("Validation issues:\n- " + "\n- ".join(issues))
    else:
        st.success("Bill table checks passed: every row and the grand total add up.")

    # ---- 2. Per line math (unchanged deriveActualAmt from webreadBillpdf.py)
    st.subheader("2. Per person split")
    try:
        billamtDF = deriveActualAmt(to_derive_frame(bill_df))
    except Exception as exc:
        st.error(f"Per line calculation failed: {exc}")
        st.stop()
    calculated = {person: round(float(amt), 2)
                  for person, amt in zip(billamtDF["Person"], billamtDF["Individual amount"])}

    # ---- 3. Manual / automatic cents adjustment
    st.subheader("3. Adjust per person amounts (optional)")
    finalDF = adjustment_editor(calculated, totalBill)

    sumofindividualamt = round(finalDF["Individual amount"].sum(), 2)
    st.write(finalDF)  # this is important print for validation. Keep it.
    st.write(f"Total Individual Amount : {sumofindividualamt}")  # this is important print for validation. Keep it.
    st.write(f"Total Bill Stmt Amount : {totalBill}")  # this is important print for validation. Keep it.
    diff = round(sumofindividualamt - totalBill, 2)
    if diff == 0:
        st.success("Per person total matches the bill exactly.")
    else:
        st.info(f"Difference vs bill: {diff:+.2f}. Use 'Auto-balance cents' or edit 'Final amount'.")

    # ---- 4. CSV download and email (unchanged validateAndSend from webreadBillpdf.py)
    st.subheader("4. Save CSV / send email")
    if not ensure_email_config():
        st.warning("Email recipients not configured: add to_address_list and main_address_list "
                   "to config.json (local) or to the app's Secrets (Streamlit Cloud).")
    validateAndSend(finalDF, totalBill, sumofindividualamt)
