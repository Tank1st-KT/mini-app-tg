import React, { useEffect, useMemo, useState } from "react";
import { authTelegram, createGeneration, createPayment, listJobs } from "./api";
import { getInitData, getTgUser, tgReadyExpand } from "./telegram";
import type { Job } from "./types";

type Tab = "generate" | "history" | "billing";

const LS_TOKEN = "miniapp_token";

export default function App() {
  const [tab, setTab] = useState<Tab>("generate");
  const [token, setToken] = useState<string>(() => localStorage.getItem(LS_TOKEN) || "");
  const [authErr, setAuthErr] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);

  // Generate
  const [prompt, setPrompt] = useState<string>("Сгенерируй 5 идей постов для Instagram про ...");
  const [genOut, setGenOut] = useState<string>("");

  // History
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsErr, setJobsErr] = useState<string>("");

  const tgUser = useMemo(() => getTgUser(), []);

  useEffect(() => {
    tgReadyExpand();
  }, []);

  useEffect(() => {
    // если уже есть токен — не авторизуемся повторно
    if (token) return;

    const initData = getInitData();
    if (!initData) {
      setAuthErr("initData не получен. Откройте приложение из Telegram.");
      return;
    }

    setBusy(true);
    authTelegram(initData)
      .then((res) => {
        localStorage.setItem(LS_TOKEN, res.token);
        setToken(res.token);
      })
      .catch(() => setAuthErr("Авторизация не прошла. Проверьте BOT_TOKEN на бэкенде и подпись initData."))
      .finally(() => setBusy(false));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    if (tab !== "history") return;

    setJobsErr("");
    setBusy(true);
    listJobs(token)
      .then(setJobs)
      .catch(() => setJobsErr("Не удалось загрузить историю (эндпоинт /jobs может быть ещё не реализован)."))
      .finally(() => setBusy(false));
  }, [token, tab]);

  async function onGenerate() {
    setGenOut("");
    setBusy(true);
    try {
      const res = await createGeneration(token, prompt);
      // Сейчас бэкенд отдаёт queued + echo. Позже замените на получение результата по job_id.
      setGenOut(JSON.stringify(res, null, 2));
    } catch {
      setGenOut("Ошибка генерации. Проверьте доступность API и авторизацию.");
    } finally {
      setBusy(false);
    }
  }

  async function onBuy(productId: string) {
    setBusy(true);
    try {
      const res = await createPayment(token, productId);
      // Редирект на провайдера оплаты
      window.location.href = res.url;
    } catch {
      alert("Платёж пока не настроен (эндпоинт /payments/create).");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container">
      <div className="card">
        <div className="row">
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>Mini App</div>
            <div className="muted small">
              Пользователь:{" "}
              {tgUser ? (
                <>
                  <span className="badge">{tgUser.id}</span>{" "}
                  <span>{tgUser.username ? `@${tgUser.username}` : (tgUser.first_name || "")}</span>
                </>
              ) : (
                <span className="badge">нет данных</span>
              )}
            </div>
          </div>
          <div style={{ maxWidth: 220 }}>
            <div className="row">
              <button className={tab === "generate" ? "" : "secondary"} onClick={() => setTab("generate")}>
                Генерация
              </button>
              <button className={tab === "history" ? "" : "secondary"} onClick={() => setTab("history")}>
                История
              </button>
              <button className={tab === "billing" ? "" : "secondary"} onClick={() => setTab("billing")}>
                Оплата
              </button>
            </div>
          </div>
        </div>

        {busy && <div className="muted small" style={{ marginTop: 8 }}>Выполняю запрос…</div>}
        {authErr && <div className="err" style={{ marginTop: 8 }}>{authErr}</div>}
      </div>

      {tab === "generate" && (
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Генерация контента</div>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Введите запрос" />
          <div className="row" style={{ marginTop: 10 }}>
            <button onClick={onGenerate} disabled={!token || busy}>
              Сгенерировать
            </button>
            <button
              className="secondary"
              onClick={() => setGenOut("")}
              disabled={busy}
            >
              Очистить
            </button>
          </div>

          {genOut && (
            <div style={{ marginTop: 10 }}>
              <div className="muted small">Ответ (пока сырой JSON, потом сделаем красивый рендер):</div>
              <pre>{genOut}</pre>
            </div>
          )}
        </div>
      )}

      {tab === "history" && (
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: 8 }}>История генераций</div>
          {jobsErr && <div className="err">{jobsErr}</div>}

          {jobs.length === 0 ? (
            <div className="muted">Пока пусто. Когда реализуете /jobs — тут появятся записи.</div>
          ) : (
            jobs.map((j) => (
              <div key={j.id} className="card" style={{ boxShadow: "none", border: "1px solid #e6e8eb" }}>
                <div className="row">
                  <div>
                    <div style={{ fontWeight: 700 }}>{j.id}</div>
                    <div className="small muted">{j.created_at}</div>
                  </div>
                  <div style={{ maxWidth: 140 }}>
                    <span className="badge">{j.status}</span>
                  </div>
                </div>
                <div style={{ marginTop: 8 }} className="small">
                  <div className="muted">Prompt:</div>
                  <div>{j.prompt}</div>
                </div>
                {j.result_text && (
                  <div style={{ marginTop: 8 }}>
                    <div className="muted small">Result:</div>
                    <pre>{j.result_text}</pre>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {tab === "billing" && (
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Оплата и тарифы</div>
          <div className="muted" style={{ marginBottom: 12 }}>
            Здесь будет витрина продуктов. Сейчас — кнопки-заглушки.
          </div>

          <div className="row">
            <button onClick={() => onBuy("credits_100")} disabled={!token || busy}>
              Купить 100 кредитов
            </button>
            <button onClick={() => onBuy("sub_month")} disabled={!token || busy} className="secondary">
              Подписка на месяц
            </button>
          </div>

          <div className="small muted" style={{ marginTop: 10 }}>
            Требуется бэкенд-эндпоинт: <span className="badge">POST /payments/create</span> → {"{ url }"} и вебхуки провайдера.
          </div>
        </div>
      )}
    </div>
  );
}
