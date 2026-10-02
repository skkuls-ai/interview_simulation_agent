import type { PointerEvent } from "react";
import type { LucideProps } from "lucide-react";
import {
  ArrowRight,
  BarChart3,
  BriefcaseBusiness,
  FileText,
  FileUser,
  MessageCircleQuestion,
  MessagesSquare,
  Mic2,
  Video,
} from "lucide-react";
import { AppShell } from "../components/AppShell";

interface StartScreenProps { onStart: () => void }

function SpeakingPersonIcon({ size = 24, color = "currentColor", strokeWidth = 2, ...props }: LucideProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <circle cx="8" cy="7.5" r="3" />
      <path d="M3.5 19c.4-3.4 2-5.2 4.5-5.2s4.1 1.8 4.5 5.2" />
      <path d="M15.2 8.2c1.2 1 1.2 2.6 0 3.6" />
      <path d="M18 5.7c2.8 2.4 2.8 6.2 0 8.6" />
    </svg>
  );
}

const competencyTiles = [
  { label: "이력서 분석", Icon: FileUser, depth: 1.1 },
  { label: "직무 분석", Icon: BriefcaseBusiness, depth: .75 },
  { label: "맞춤 질문", Icon: MessageCircleQuestion, depth: 1.35 },
  { label: "음성 답변", Icon: Mic2, depth: .9 },
  { label: "영상 면접", Icon: Video, depth: 1.2 },
  { label: "결과 피드백", Icon: SpeakingPersonIcon, depth: .7 },
];

export function StartScreen({ onStart }: StartScreenProps) {
  const moveCompetencyTiles = (event: PointerEvent<HTMLElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width - .5;
    const y = (event.clientY - bounds.top) / bounds.height - .5;

    event.currentTarget.querySelectorAll<HTMLElement>(".competency-tile").forEach((tile) => {
      const depth = Number(tile.dataset.depth ?? 1);
      tile.style.setProperty("--parallax-x", `${x * 18 * depth}px`);
      tile.style.setProperty("--parallax-y", `${y * 14 * depth}px`);
    });
  };

  const resetCompetencyTiles = (event: PointerEvent<HTMLElement>) => {
    event.currentTarget.querySelectorAll<HTMLElement>(".competency-tile").forEach((tile) => {
      tile.style.setProperty("--parallax-x", "0px");
      tile.style.setProperty("--parallax-y", "0px");
    });
  };

  return (
    <AppShell>
      <section className="start-hero" onPointerMove={moveCompetencyTiles} onPointerLeave={resetCompetencyTiles}>
        <div className="competency-field" aria-hidden="true">
          {competencyTiles.map(({ label, Icon, depth }, index) => (
            <div key={label} className={`competency-tile competency-tile-${index + 1}`} data-depth={depth}>
              <div className="competency-tile-body">
                <Icon size={30} strokeWidth={1.9} />
                <span>{label}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="start-copy">
          <h1>면까몰</h1>
          <p className="hero-tagline">면접은 까보기 전에 모른다.</p>
          <button className="button button-primary start-button" type="button" onClick={onStart}>
            면접 까러가기 <ArrowRight size={17} />
          </button>
        </div>
      </section>

      <section className="start-values" aria-labelledby="start-values-title">
        <div className="value-intro">
          <h2 id="start-values-title">연습의 흐름은<br />단순하게.</h2>
        </div>
        <div className="value-list">
          <article>
            <span className="value-index">01</span>
            <FileText size={22} aria-hidden="true" />
            <h3>내 경험에서 시작하는 질문</h3>
            <p>채용공고와 지원서류를 바탕으로 지금 나에게 필요한 질문을 준비합니다.</p>
          </article>
          <article>
            <span className="value-index">02</span>
            <MessagesSquare size={22} aria-hidden="true" />
            <h3>실전처럼 말하는 연습</h3>
            <p>생각할 시간부터 꼬리질문까지, 실제 면접의 호흡으로 답해봅니다.</p>
          </article>
          <article>
            <span className="value-index">03</span>
            <BarChart3 size={22} aria-hidden="true" />
            <h3>다음 답변이 달라지는 피드백</h3>
            <p>답변의 근거와 전달 방식을 함께 살펴보고 개선할 지점을 발견합니다.</p>
          </article>
        </div>
      </section>
    </AppShell>
  );
}
