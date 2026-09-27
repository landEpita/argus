"use client";

import { useState } from "react";
import { CyberPanel } from "@/components/intel/CyberPanel";
import { NewsPanel } from "@/components/intel/NewsPanel";
import { TelegramPanel } from "@/components/intel/TelegramPanel";
import type { CountryDirectory } from "@/features/intel/countries";
import type { Situation } from "@/features/map/situations";
import type { ApiClient } from "@/lib/api/client";
import { MiniMarkets } from "./MiniMarkets";
import { SituationsList } from "./SituationsList";

type Tab = "situations" | "news" | "telegram" | "cyber" | "markets";
const TABS: { id: Tab; label: string }[] = [
  { id: "situations", label: "Situations" },
  { id: "news", label: "News" },
  { id: "telegram", label: "Telegram" },
  { id: "cyber", label: "Cyber" },
  { id: "markets", label: "Markets" },
];

interface Props {
  api: ApiClient;
  countries: CountryDirectory;
  channels: readonly string[];
  onChannelsChange(channels: string[]): void;
  focused: string | null;
  onFocusSituation(situation: Situation): void;
  onFocusCountry(iso2: string): void;
  onOpenMarkets(): void;
  onClose(): void;
}

/** The left panel of the map. Only the open tab polls its source. */
export function RightNowPanel(props: Props) {
  const [tab, setTab] = useState<Tab>("situations");
  const { api, countries } = props;
  return (
    <aside className="side-card rightnow glass" aria-label="Right now">
      <div className="card-head">
        <div>
          <h2>Right now</h2>
          <p>Converging signals, news and feeds</p>
        </div>
        <button type="button" className="icon-btn" aria-label="Hide panel" onClick={props.onClose}>
          ‹
        </button>
      </div>
      <div role="tablist" aria-label="Feeds" className="card-tabs segmented">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="card-body">
        {tab === "situations" && (
          <SituationsList
            api={api}
            countries={countries}
            focused={props.focused}
            onFocus={props.onFocusSituation}
          />
        )}
        {tab === "news" && (
          <NewsPanel api={api} countries={countries} onFocusCountry={props.onFocusCountry} />
        )}
        {tab === "telegram" && (
          <TelegramPanel
            api={api}
            channels={props.channels}
            onChannelsChange={props.onChannelsChange}
            countries={countries}
            onFocusCountry={props.onFocusCountry}
          />
        )}
        {tab === "cyber" && <CyberPanel api={api} />}
        {tab === "markets" && <MiniMarkets api={api} onOpen={props.onOpenMarkets} />}
      </div>
    </aside>
  );
}
