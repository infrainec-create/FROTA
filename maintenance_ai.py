"""Analista de manutenção com a Responses API."""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI


def compact_vehicle_context(
    vehicle: dict[str, Any] | None,
    maintenance: list[dict[str, Any]],
    fuel: list[dict[str, Any]],
    expenses: list[dict[str, Any]] | None = None,
    tires_list: list[dict[str, Any]] | None = None,
    vehicles_list: list[dict[str, Any]] | None = None
) -> str:
    """Compacta e limpa os dados brutos enviando apenas informações essenciais para economizar até 85% de tokens."""
    if vehicle is None:
        v_summary = []
        for v in (vehicles_list or []):
            v_summary.append({
                "marca_modelo": f"{v.get('brand', '')} {v.get('model', '')}".strip() or v.get("name"),
                "placa": v.get("plate"),
                "ano": v.get("year"),
                "status": v.get("status")
            })
            
        maint_summary = [{
            "tipo": m.get("maint_type"),
            "servico": m.get("description"),
            "custo": m.get("cost"),
            "km": m.get("odometer"),
            "data": m.get("maint_date")
        } for m in maintenance[-15:]]
        
        tires_summary = [{
            "pos": t.get("position"),
            "marca": t.get("brand"),
            "sulco_mm": t.get("current_tread_mm")
        } for t in (tires_list or [])[-15:]]

        return json.dumps({
            "frota": v_summary[:15],
            "manutencoes_recentes": maint_summary,
            "pneus_inspecionados": tires_summary
        }, ensure_ascii=False, default=str)
    else:
        v_clean = {
            "marca": vehicle.get("brand") or vehicle.get("name"),
            "modelo": vehicle.get("model") or vehicle.get("name"),
            "versao": vehicle.get("version"),
            "combustivel": vehicle.get("fuel_type"),
            "ano": vehicle.get("year"),
            "placa": vehicle.get("plate"),
            "odometro_inicial": vehicle.get("initial_odometer"),
            "meta_km_l": vehicle.get("target_consumption"),
            "revisao_km": vehicle.get("maint_interval_km")
        }
        v_clean = {k: v for k, v in v_clean.items() if v is not None and str(v).strip() != ""}

        maint_clean = [{
            "servico": m.get("description"),
            "custo": m.get("cost"),
            "km": m.get("odometer"),
            "data": m.get("maint_date")
        } for m in maintenance[-10:]]

        fuel_clean = [{
            "litros": f.get("liters"),
            "custo": f.get("cost"),
            "km": f.get("odometer")
        } for f in fuel[-5:]]

        tires_clean = [{
            "pos": t.get("position"),
            "marca": t.get("brand"),
            "sulco_mm": t.get("current_tread_mm")
        } for t in (tires_list or [])]

        return json.dumps({
            "veiculo": v_clean,
            "historico_manutencao": maint_clean,
            "ultimos_abastecimentos": fuel_clean,
            "pneus": tires_clean
        }, ensure_ascii=False, default=str)


def analyze_maintenance(
    api_key: str,
    vehicle: dict[str, Any] | None,
    maintenance: list[dict[str, Any]],
    fuel: list[dict[str, Any]],
    mode: str = "general",
    vehicles_list: list[dict[str, Any]] | None = None,
    expenses: list[dict[str, Any]] | None = None,
    tires_list: list[dict[str, Any]] | None = None,
    provider: str = "gemini"
) -> str:
    """Gera um parecer de apoio, plano de manutenção preventiva ou previsão orçamentária; nunca toma decisões operacionais automaticamente."""
    # Compactar contexto reduzindo consumo de tokens em até 85%
    context = compact_vehicle_context(vehicle, maintenance, fuel, expenses, tires_list, vehicles_list)

    if vehicle is None:
        if mode == "budget":
            system_content = (
                "Você é um especialista em planejamento financeiro e orçamento de frotas corporativas. "
                "Com base no histórico recente de toda a frota de veículos (abastecimentos, manutenções e outras despesas operacionais como pedágios, estacionamentos e lavagens), "
                "projete o orçamento estimado para o PRÓXIMO MÊS de toda a frota de forma consolidada. "
                "Responda em português do Brasil. Divida a estimativa por categorias (Combustível, Manutenção, Outros), "
                "aponte possíveis desvios orçamentários, e sugira 3 ações estratégicas corporativas para redução de custos. "
                "Formate de maneira elegante utilizando tabelas em markdown. "
                "Termine com: 'Esta projeção orçamentária é baseada em dados estatísticos passados e estimativas de mercado da frota.'"
            )
        elif mode == "plan":
            system_content = (
                "Você é um engenheiro especialista em gestão de frotas corporativas. Responda em português do Brasil. "
                "Monte um PLANO CONSOLIDADO DE MANUTENÇÃO PREVENTIVA E DIRETRIZES DE REVISÃO para a frota completa fornecida. "
                "Identifique quais veículos estão com maior prioridade de revisão, sugira a periodicidade recomendada "
                "por modelo de veículo e apresente uma tabela estruturada em markdown dividida por severidade e odômetros de revisão. "
                "Termine com: 'Este plano de manutenção consolidado é gerado por inteligência artificial como diretriz de planejamento corporativo.'"
            )
        else:
            system_content = (
                "Você é um analista de manutenção de frota corporativa. Responda em português do Brasil. "
                "Avalie padrões de custo, frequência de manutenção de toda a frota de forma consolidada, considerando também custos extras/diversos e estado dos pneus. "
                "Aponte quais veículos ou tipos de despesa representam maior risco de custo ou paradas operacionais. "
                "Classifique os riscos de frota em Crítico, Atenção ou Monitorar e forneça ações objetivas. "
                "Não invente dados. Termine com: 'Este parecer é apoio à decisão de frota e não substitui a inspeção técnica individual de profissionais.'"
            )
    else:
        # Single vehicle analysis
        if mode == "budget":
            system_content = (
                "Você é um especialista em planejamento financeiro e orçamento de frotas. "
                "Com base no histórico de custos de combustível, manutenção e outras despesas fornecidos, projete "
                "o orçamento estimado para o PRÓXIMO MÊS deste veículo. Responda em português do Brasil. "
                "Divida a estimativa por categorias (Combustível, Manutenção, Outros), aponte possíveis riscos orçamentários "
                "e sugira 3 ações práticas de redução de custos. Formate de maneira elegante utilizando tabelas em markdown. "
                "Termine com: 'Esta projeção orçamentária é baseada em dados estatísticos passados e estimativas de mercado.'"
            )
        elif mode == "plan":
            system_content = (
                "Você é um engenheiro automotivo sênior especialista em frotas corporativas. Responda em português do Brasil. "
                "Sua missão é criar um PLANO DE MANUTENÇÃO PREVENTIVA PERSONALIZADO E DETALHADO para o veículo fornecido "
                "(levando em conta sua marca, modelo, ano, odômetro atual, histórico de manutenções e estado dos pneus).\n\n"
                "Siga obrigatoriamente estes 4 passos:\n"
                "1. **Identificação do Modelo**: Reconheça as especificações da marca/modelo do veículo e os intervalos recomendados pela montadora.\n"
                "2. **Cronograma de Revisões (Tabela Markdown)**: Crie uma tabela de revisões por faixas de odômetro (ex: 10.000 km, 20.000 km, 40.000 km, 60.000 km, 100.000 km), listando os itens a inspecionar/substituir (Óleo de Motor, Filtros de Ar/Óleo/Combustível, Correia Dentada/Corrente, Fluidos de Freio/Arrefecimento, Velas/Injetores, Pastilhas/Discos, Suspensão, Geometria e Rodízio de Pneus).\n"
                "3. **Diagnóstico em Relação ao Odômetro Atual e Histórico Real**: Compare o plano com o odômetro atual e registros passados, destacando:\n"
                "   - 🔴 **Serviços Atrasados/Pendentes**\n"
                "   - ⚠️ **Próxima Revisão Imediata** (em quantos KM e prazo estimado)\n"
                "   - 🟢 **Serviços Recentes em Dia**\n"
                "4. **Recomendações Práticas**: Forneça 3 orientações técnicas específicas de uso e conservação para a marca/modelo deste veículo.\n\n"
                "Termine com: 'Este plano de manutenção preventiva personalizado é gerado por inteligência artificial com base nas especificações técnicas do veículo e histórico de operação da frota.'"
            )
        else:
            system_content = (
                "Você é um analista de manutenção de frota. Responda em português do Brasil, "
                "usando somente os registros recebidos. Avalie padrões de custo, frequência, despesas extras, estado dos pneus e "
                "quilometragem; priorize riscos em Crítico, Atenção ou Monitorar e dê ações objetivas. "
                "Não invente falhas ou dados. Informe incertezas. Termine com: 'Este parecer é apoio "
                "à decisão e não substitui a inspeção de um profissional qualificado.'"
            )

    clean_key = api_key.strip()
    if provider == "gemini":
        client = OpenAI(
            api_key=clean_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai"
        )
        gemini_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        last_err = None
        for g_model in gemini_models:
            try:
                response = client.chat.completions.create(
                    model=g_model,
                    max_tokens=1200,
                    messages=[
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": f"Analise os dados e monte o plano de manutenção desta frota/veículo:\n{context}"}
                    ]
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                last_err = e
                err_text = str(e).lower()
                if "404" in err_text or "not_found" in err_text:
                    continue
                raise e
        if last_err:
            raise last_err
    else:
        client = OpenAI(api_key=clean_key)
        model_name = "gpt-4o-mini"
        response = client.chat.completions.create(
            model=model_name,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": f"Analise os dados e monte o plano de manutenção desta frota/veículo:\n{context}"}
            ]
        )
        return response.choices[0].message.content or ""
