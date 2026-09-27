"use client";

import { AlertsFeed } from "@/components/alerts/AlertsFeed";
import { CyberPanel } from "@/components/intel/CyberPanel";
import { NewsPanel } from "@/components/intel/NewsPanel";
import { TelegramPanel } from "@/components/intel/TelegramPanel";
import type { CountryDirectory } from "@/features/intel/countries";
import type { Situation } from "@/features/map/situations";
import type { ApiClient } from "@/lib/api/client";
import type { AlertItem } from "@/lib/api/types";
import { MiniMarkets } from "./MiniMarkets";
import { SituationsList } from "./SituationsList";

export type RightNowTab = "situations" | "alerts" | "news" | "telegram" | "cyber" | "markets";
type Tab = RightNowTab;
const TABS: { id: Tab; label: string }[] = [
  { id: "situations", label: "Situations" },
  { id: "alerts", label: "Alerts" },
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
  tab: Tab;
  onTab(tab: Tab): void;
  unread: number;
  onOpenAlert(alert: AlertItem): void;
  onManageAlerts(): void;
}

/** The left panel of the map. Only the open tab polls its source. */
export function RightNowPanel(props: Props) {
  const { api, countries, tab } = props;
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
            onClick={() => props.onTab(t.id)}
          >
            {t.label}
            {t.id === "alerts" && props.unread > 0 ? ` · ${props.unread}` : ""}
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
        {tab === "alerts" && (
          <AlertsFeed api={api} onOpen={props.onOpenAlert} onManage={props.onManageAlerts} />
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
