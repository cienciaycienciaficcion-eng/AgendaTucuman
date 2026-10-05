            articles, state["selected_ids"], len(candidate_ids), 0
        )
        save_state(state)
        return

    run_budget = max(gemini_budget, groq_budget)
    batch = pending[:run_budget]

    print(
        f"[IA Servicios] Pendientes: {len(pending)}. "
        f"Cuota Gemini: {remaining_gemini}, cuota Groq: {remaining_groq}. "
        f"Esta corrida procesará como máximo {len(batch)} artículos."
    )


    calls = 0
    selected_this_run = 0
    gemini_available = bool(gemini_api_key) and gemini_budget > 0

    for index, article in enumerate(batch, start=1):
        # Espaciado individual para evitar ráfagas de solicitudes.
        # No esperamos antes del primer artículo.
        if index > 1:
            wait = GEMINI_MIN_INTERVAL_SECONDS + random.uniform(
                0, GEMINI_JITTER_SECONDS
            )
            print(
                f"[IA Servicios] Esperando {wait:.1f}s antes del artículo "
                f"{index}/{len(batch)}..."
            )
            time.sleep(wait)

        sid = str(article.get("id"))
        calls += 1
        try:
            if gemini_available:
                try:
                    result = ask_gemini(article, state)
                    provider = "gemini"
                except Exception as gemini_error:
                    print(f"[Gemini Servicios] Falló Gemini: {gemini_error}")
                    # Ante cualquier fallo de Gemini, se pasa a Groq para este
                    # artículo y se desactiva Gemini para el resto de la corrida.
                    # Así evitamos consumir reintentos inútiles cuando la API
                    # está sin cuota, caída o mal configurada.
                    gemini_available = False
                    if isinstance(gemini_error, requests.HTTPError):
                        status = (
                            gemini_error.response.status_code
                            if gemini_error.response is not None
                            else None
                        )
                        if status == 429:
                            print(
                                "[Gemini Servicios] 429/cuota detectado: "
                                "Gemini queda desactivado para esta corrida."
                            )
                    print("[Gemini Servicios] Probando Groq como fallback...")
                    try:
                        result = ask_groq(article, state)
                        provider = "groq"
                        print(f"[Groq Servicios] OK: {article.get('title', '')}")
                    except Exception as groq_error:
                        print(f"[Groq Servicios] También falló: {groq_error}")
                        raise RuntimeError(
                            f"Gemini y Groq fallaron para {article.get('title', '')}"
                        ) from groq_error
            else:
                print(
                    "[Gemini Servicios] No disponible en esta corrida; "
                    "usando Groq."
                )
                try:
                    result = ask_groq(article, state)
                    provider = "groq"
                    print(f"[Groq Servicios] OK: {article.get('title', '')}")
                except Exception as groq_error:
                    print(f"[Groq Servicios] Falló: {groq_error}")
                    raise

            if isinstance(result, dict):
                result["provider"] = provider
            selected = bool(result.get("selected", False))
            state["processed"][sid] = {
                "selected": selected,
                "processed_at": now_utc().isoformat(),
                "content_hash": article_content_hash(article),
                "provider": provider,
                "reason": str(result.get("reason", ""))[:300],
            }

            # Si el artículo fue reevaluado y ya no corresponde, retirarlo.
            if not selected and sid in state["selected_ids"]:
                state["selected_ids"].remove(sid)
            if selected and sid not in state["selected_ids"]:
                state["selected_ids"].append(sid)
                selected_this_run += 1
            print(
                f"[IA Servicios] {calls}/{len(batch)} "
                f"ID={sid} selected={selected}"
            )
        except requests.HTTPError as exc:
            # No marcar como procesado: se reintentará en la siguiente corrida.
            print(f"[Gemini Servicios] HTTP error para {sid}: {exc}")
            continue
        except Exception as exc:
            # Tampoco se marca como procesado si la llamada no pudo completarse.
            print(f"[Gemini Servicios] Error para {sid}: {exc}")
            continue

    state["selected_ids"] = write_output(
        articles,
        state["selected_ids"],
        len(candidate_ids),
        calls,
    )
    save_state(state)

    remaining = sum(
        1 for a in candidates
        if str(a.get("id")) not in state["processed"]
    )
    print(
        f"[IA Servicios] Fin de corrida: llamadas={calls}, "
        f"nuevos seleccionados={selected_this_run}, pendientes={remaining}, "
        f"publicados={len(state['selected_ids'])}."
    )
