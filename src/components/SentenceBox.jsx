import { renderStressed } from '../lib/stress'

export default function SentenceBox({ sentence, revealed }) {
  if (!revealed) return <div className="sentence-box"><div className="cover">🔇 原文已隐藏</div></div>
  return <div className="sentence-box"><div className="txt ru" dangerouslySetInnerHTML={{ __html: renderStressed(sentence.russian) }} /></div>
}
