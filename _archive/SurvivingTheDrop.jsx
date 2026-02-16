import React, { useState, useEffect } from 'react';

export default function SurvivingTheDropFinal() {
  const [activeTab, setActiveTab] = useState('zones');
  const [countdown, setCountdown] = useState({ days: 0, hours: 0, minutes: 0, seconds: 0 });
  const [selectedMarker, setSelectedMarker] = useState(null);
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [showProModal, setShowProModal] = useState(false);
  const [email, setEmail] = useState('');
  const [emailSubmitted, setEmailSubmitted] = useState(false);
  const [checkedItems, setCheckedItems] = useState({});
  const [showMascot, setShowMascot] = useState(true);

  // Show email modal after 20 seconds
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!emailSubmitted && !localStorage.getItem('std_email_captured')) {
        setShowEmailModal(true);
      }
    }, 20000);
    return () => clearTimeout(timer);
  }, [emailSubmitted]);

  // Countdown to NYE 2026
  useEffect(() => {
    const targetDate = new Date('2026-01-01T00:00:00-05:00');
    const updateCountdown = () => {
      const now = new Date();
      const diff = targetDate - now;
      if (diff > 0) {
        setCountdown({
          days: Math.floor(diff / (1000 * 60 * 60 * 24)),
          hours: Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)),
          minutes: Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60)),
          seconds: Math.floor((diff % (1000 * 60)) / 1000)
        });
      }
    };
    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleEmailSubmit = (e) => {
    e.preventDefault();
    if (email) {
      localStorage.setItem('std_email_captured', 'true');
      setEmailSubmitted(true);
      setShowEmailModal(false);
    }
  };

  const formatNum = (n) => String(n).padStart(2, '0');
  const toggleItem = (key) => setCheckedItems(prev => ({ ...prev, [key]: !prev[key] }));

  // Cute Kumquat Mascot SVG Component
  const KumquatMascot = ({ mood = 'happy', size = 60, className = '' }) => (
    <svg width={size} height={size} viewBox="0 0 100 100" className={className}>
      {/* Body */}
      <ellipse cx="50" cy="55" rx="35" ry="40" fill="url(#kumquatGradient)" />
      {/* Highlight */}
      <ellipse cx="38" cy="40" rx="12" ry="15" fill="rgba(255,255,255,0.3)" />
      {/* Leaf */}
      <ellipse cx="50" cy="18" rx="8" ry="12" fill="#4ade80" transform="rotate(-15 50 18)" />
      <ellipse cx="58" cy="16" rx="6" ry="10" fill="#22c55e" transform="rotate(20 58 16)" />
      {/* Face */}
      {mood === 'happy' && (
        <>
          <circle cx="38" cy="50" r="4" fill="#1e293b" />
          <circle cx="62" cy="50" r="4" fill="#1e293b" />
          <path d="M 40 65 Q 50 75 60 65" stroke="#1e293b" strokeWidth="3" fill="none" strokeLinecap="round" />
        </>
      )}
      {mood === 'cold' && (
        <>
          <circle cx="38" cy="50" r="4" fill="#1e293b" />
          <circle cx="62" cy="50" r="4" fill="#1e293b" />
          <ellipse cx="50" cy="68" rx="8" ry="5" fill="#1e293b" />
          {/* Scarf */}
          <path d="M 25 70 Q 50 80 75 70" stroke="#ef4444" strokeWidth="8" fill="none" />
          <rect x="70" y="68" width="8" height="20" rx="2" fill="#ef4444" />
        </>
      )}
      {mood === 'warning' && (
        <>
          <circle cx="38" cy="50" r="5" fill="#1e293b" />
          <circle cx="62" cy="50" r="5" fill="#1e293b" />
          <ellipse cx="50" cy="70" rx="10" ry="6" fill="#1e293b" />
        </>
      )}
      <defs>
        <linearGradient id="kumquatGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#fbbf24" />
          <stop offset="50%" stopColor="#f97316" />
          <stop offset="100%" stopColor="#ea580c" />
        </linearGradient>
      </defs>
    </svg>
  );

  // Crowd Illustration SVG
  const CrowdIllustration = () => (
    <svg viewBox="0 0 400 100" className="w-full h-16 opacity-30">
      {[...Array(40)].map((_, i) => (
        <g key={i} transform={`translate(${i * 10 + Math.random() * 5}, ${50 + Math.random() * 30})`}>
          <circle r={4 + Math.random() * 3} fill={`hsl(${200 + Math.random() * 60}, 70%, ${50 + Math.random() * 20}%)`} />
          <rect x="-3" y="5" width="6" height={10 + Math.random() * 5} rx="2" fill={`hsl(${200 + Math.random() * 60}, 60%, ${40 + Math.random() * 20}%)`} />
        </g>
      ))}
    </svg>
  );

  // Data
  const zones = [
    { id: 'a', name: 'Zone A - Premium', rating: 5, fillTime: '11 AM - 1 PM', wait: '10-12 hours', view: 'Direct ball view', street: '43rd St entry', tip: 'For hardcore fans only. Arrive before noon or forget it.', color: 'from-amber-400 to-orange-500' },
    { id: 'b', name: 'Zone B - Great', rating: 4, fillTime: '1 PM - 3 PM', wait: '8-10 hours', view: 'Excellent ball + stage', street: '44th St entry', tip: 'Best balance of view vs. suffering. Our recommendation.', color: 'from-cyan-400 to-blue-500', recommended: true },
    { id: 'c', name: 'Zone C - Good', rating: 3, fillTime: '3 PM - 5 PM', wait: '6-8 hours', view: 'Ball visible, big screens', street: '45th St entry', tip: 'Solid choice for first-timers. Less brutal wait.', color: 'from-emerald-400 to-green-500' },
    { id: 'd', name: 'Zone D - Screens', rating: 2, fillTime: '5 PM - 7 PM', wait: '4-6 hours', view: 'Screens only', street: '46th-47th St entry', tip: 'You\'re here for the vibe, not the view. That\'s valid.', color: 'from-purple-400 to-pink-500' },
  ];

  const mistakes = [
    { icon: '🎒', title: 'Bringing a backpack', desc: 'Banned at security. Use pockets or tiny clear bag.', severity: 'high' },
    { icon: '☕', title: 'Drinking lots of fluids', desc: 'No bathrooms = major problem. Minimize after noon.', severity: 'high' },
    { icon: '🕐', title: 'Arriving after 3 PM', desc: 'You\'ll watch on screens from 47th street.', severity: 'high' },
    { icon: '📱', title: 'Relying on cell service', desc: '1M+ people kills the network. Download offline.', severity: 'medium' },
    { icon: '👟', title: 'Fashion over function', desc: '10+ hours standing in 25°F. Dress for survival.', severity: 'medium' },
    { icon: '🚶', title: 'Thinking you can leave', desc: 'Exit pen = lose spot forever. No re-entry.', severity: 'high' },
    { icon: '🍕', title: 'Planning to grab food', desc: 'Nothing accessible once pens fill. Bring everything.', severity: 'medium' },
    { icon: '🚕', title: 'Uber/Lyft after', desc: 'Streets closed for miles. Walk or wait 2+ hours.', severity: 'low' },
  ];

  const bringItems = [
    { name: 'Hand warmers (10+ pairs)', critical: true, category: 'warmth' },
    { name: 'Toe warmers (5+ pairs)', critical: true, category: 'warmth' },
    { name: 'Thermal base layers', critical: true, category: 'warmth' },
    { name: 'Insulated waterproof boots', critical: true, category: 'warmth' },
    { name: 'Adult diapers or pads', critical: true, category: 'survival' },
    { name: 'Portable charger (full)', critical: true, category: 'tech' },
    { name: 'High-calorie snacks', critical: true, category: 'food' },
    { name: 'Photo ID', critical: true, category: 'essential' },
    { name: 'Balaclava / ski mask', critical: false, category: 'warmth' },
    { name: 'Touchscreen gloves', critical: false, category: 'warmth' },
    { name: 'Frozen water bottles', critical: false, category: 'food' },
    { name: 'Small seat cushion', critical: false, category: 'comfort' },
    { name: 'Cash (small bills)', critical: false, category: 'essential' },
    { name: 'Offline entertainment', critical: false, category: 'tech' },
  ];

  const dontBring = [
    { name: 'Backpacks / large bags', reason: 'Banned' },
    { name: 'Umbrellas', reason: 'Prohibited' },
    { name: 'Alcohol', reason: 'Arrest risk' },
    { name: 'Chairs / blankets', reason: 'Not allowed' },
    { name: 'Glass containers', reason: 'Confiscated' },
    { name: 'Large cameras', reason: 'May be banned' },
  ];

  const survivalHacks = [
    { icon: '🩲', title: 'The Uncomfortable Truth', desc: 'Adult diapers aren\'t a joke. Veterans swear by Depend or Always Discreet. Your dignity vs. 10 hours of suffering.', pro: false, category: 'bathroom' },
    { icon: '💧', title: 'Fluid Management', desc: 'Stop drinking by 10 AM. Small sips only. Yes, dehydration is a risk, but so is desperation.', pro: false, category: 'bathroom' },
    { icon: '🏨', title: 'Hotel Bathroom Map', desc: 'We\'ve mapped hotels allowing non-guest bathroom access before 2 PM.', pro: true, category: 'bathroom' },
    { icon: '🥜', title: 'Calorie Strategy', desc: 'Nuts, protein bars, jerky. Need 500-800 calories. No smelly foods—you\'re packed tight.', pro: false, category: 'food' },
    { icon: '🧊', title: 'Frozen Bottle Trick', desc: 'Freeze bottles overnight. They thaw slowly, stay cold, won\'t spill in pockets.', pro: false, category: 'food' },
    { icon: '☕', title: 'Thermos Strategy', desc: 'Hot cocoa or soup, sip sparingly. Warmth > caffeine (caffeine = bathroom needs).', pro: false, category: 'food' },
    { icon: '🍽️', title: 'Pre-Event Dining Guide', desc: 'Best spots for a big meal before committing. Reservation tips included.', pro: true, category: 'food' },
    { icon: '🚪', title: 'Secret Exit Routes', desc: 'Fastest ways out after midnight to avoid the worst crowds.', pro: true, category: 'exit' },
  ];

  const mapMarkers = [
    { id: 'ball', x: 50, y: 70, type: 'ball', label: 'The Ball', desc: 'One Times Square - Where magic happens at midnight.' },
    { id: 'zonea', x: 40, y: 58, type: 'zone', zone: 'A', label: 'Zone A', desc: 'Premium viewing. First to fill. 11 AM arrival.' },
    { id: 'zoneb', x: 48, y: 46, type: 'zone', zone: 'B', label: 'Zone B', desc: 'Great views. Recommended. Arrive by 1 PM.' },
    { id: 'zonec', x: 52, y: 34, type: 'zone', zone: 'C', label: 'Zone C', desc: 'Good views + screens. Arrive by 3 PM.' },
    { id: 'zoned', x: 45, y: 22, type: 'zone', zone: 'D', label: 'Zone D', desc: 'Screen viewing. Arrive by 5 PM.' },
    { id: 'entry1', x: 25, y: 75, type: 'entry', label: '42nd Entry', desc: 'Main checkpoint. Longest lines.' },
    { id: 'entry2', x: 68, y: 52, type: 'entry', label: '44th Entry', desc: 'Less crowded. Our pick.' },
    { id: 'entry3', x: 28, y: 28, type: 'entry', label: '46th Entry', desc: 'Northern entry for Zones C & D.' },
  ];

  const timeline = [
    { time: '11 AM', event: 'Streets Close', desc: 'Barriers up. Zone A diehards arrive.', phase: 'early' },
    { time: '1 PM', event: 'Pens Open', desc: 'Security activates. Zone A fills fast.', phase: 'early' },
    { time: '3 PM', event: 'Zone A Full', desc: 'Zone B filling. Last good spots.', phase: 'mid' },
    { time: '5 PM', event: 'B & C Full', desc: 'Only Zone D remains.', phase: 'mid' },
    { time: '6 PM', event: 'Shows Start', desc: 'Live performances begin.', phase: 'late' },
    { time: '11:59', event: 'THE DROP', desc: '60-second countdown! 🎊', phase: 'finale' },
  ];

  // Components
  const ProBadge = () => (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-gradient-to-r from-amber-400 to-orange-500 text-white text-[10px] font-bold rounded-full shadow-lg shadow-orange-500/25">
      ⭐ PRO
    </span>
  );

  const TabButton = ({ id, icon, label, active }) => (
    <button
      onClick={() => setActiveTab(id)}
      className={`flex flex-col items-center gap-1 px-3 py-2 rounded-xl font-medium transition-all min-w-[70px] ${
        active
          ? 'bg-gradient-to-br from-orange-400 to-amber-500 text-white shadow-lg shadow-orange-500/30 scale-105'
          : 'bg-slate-800/70 text-slate-400 hover:bg-slate-700 hover:text-slate-200'
      }`}
    >
      <span className="text-lg">{icon}</span>
      <span className="text-[10px] uppercase tracking-wide">{label}</span>
    </button>
  );

  // Modals
  const EmailModal = () => (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowEmailModal(false)}>
      <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-orange-500/30 rounded-3xl p-6 max-w-sm w-full relative shadow-2xl" onClick={e => e.stopPropagation()}>
        <button onClick={() => setShowEmailModal(false)} className="absolute top-4 right-4 text-slate-400 hover:text-white text-xl">×</button>
        <div className="text-center mb-5">
          <KumquatMascot mood="cold" size={80} className="mx-auto mb-3" />
          <h3 className="text-xl font-bold mb-1">Don't Freeze Unprepared!</h3>
          <p className="text-slate-400 text-sm">Get our <span className="text-orange-400 font-semibold">FREE printable checklist</span> + last-minute tips before NYE.</p>
        </div>
        <form onSubmit={handleEmailSubmit} className="space-y-3">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="your@email.com"
            className="w-full px-4 py-3 bg-slate-700/50 border border-slate-600 rounded-xl focus:border-orange-500 focus:outline-none focus:ring-2 focus:ring-orange-500/20"
            required
          />
          <button type="submit" className="w-full py-3 bg-gradient-to-r from-orange-500 to-amber-500 rounded-xl font-bold hover:opacity-90 transition-all shadow-lg shadow-orange-500/25">
            Send Me The Checklist 📋
          </button>
        </form>
        <p className="text-[10px] text-slate-500 text-center mt-3">No spam. Unsubscribe anytime.</p>
      </div>
    </div>
  );

  const ProModal = () => (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowProModal(false)}>
      <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-amber-500/30 rounded-3xl p-6 max-w-sm w-full relative shadow-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <button onClick={() => setShowProModal(false)} className="absolute top-4 right-4 text-slate-400 hover:text-white text-xl">×</button>
        <div className="text-center mb-5">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-gradient-to-r from-amber-400 to-orange-500 rounded-full text-sm font-bold mb-3">⭐ PRO VERSION</div>
          <h3 className="text-xl font-bold">Surviving The Drop PRO</h3>
          <p className="text-slate-400 text-sm mt-1">The intel that makes the difference.</p>
        </div>
        <ul className="space-y-2 mb-5 text-sm">
          {['Hotel bathroom access map', 'Public restroom locations', 'Pre-event restaurant guide', 'Printable pocket survival card', 'Offline PDF (no wifi needed)', 'Secret exit routes', 'Group coordination planner'].map((item, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className="text-green-400 text-lg">✓</span> {item}
            </li>
          ))}
        </ul>
        <div className="text-center mb-4">
          <div className="text-3xl font-black bg-gradient-to-r from-amber-400 to-orange-500 bg-clip-text text-transparent">$4.99</div>
          <div className="text-slate-500 text-xs">One-time • Instant access</div>
        </div>
        <button className="w-full py-3 bg-gradient-to-r from-amber-400 to-orange-500 rounded-xl font-bold hover:opacity-90 transition-all shadow-lg shadow-orange-500/25">
          Get PRO Access →
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 text-white overflow-x-hidden">
      {showEmailModal && <EmailModal />}
      {showProModal && <ProModal />}

      {/* Ambient Effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -left-40 w-80 h-80 bg-orange-500/10 rounded-full blur-3xl"></div>
        <div className="absolute top-1/3 -right-20 w-60 h-60 bg-cyan-500/10 rounded-full blur-3xl"></div>
        <div className="absolute -bottom-20 left-1/3 w-72 h-72 bg-purple-500/10 rounded-full blur-3xl"></div>
      </div>

      <div className="relative z-10 max-w-lg mx-auto px-4 py-5">
        
        {/* Header */}
        <header className="text-center mb-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-slate-800/80 border border-slate-700 rounded-full text-xs mb-3">
            <span>🗽</span>
            <span className="text-slate-300">NYE 2026 • TIMES SQUARE</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight mb-2">
            <span className="bg-gradient-to-r from-cyan-300 via-white to-cyan-300 bg-clip-text text-transparent">SURVIVING</span>
            <br />
            <span className="bg-gradient-to-r from-orange-400 via-amber-300 to-orange-400 bg-clip-text text-transparent">THE DROP</span>
          </h1>
          <p className="text-slate-400 text-sm">Because winging it is not a strategy.</p>
        </header>

        {/* Countdown */}
        <div className="flex justify-center gap-2 mb-5">
          {[
            { val: countdown.days, label: 'DAYS', color: 'from-cyan-500 to-blue-600' },
            { val: countdown.hours, label: 'HRS', color: 'from-purple-500 to-pink-600' },
            { val: countdown.minutes, label: 'MIN', color: 'from-orange-500 to-amber-500' },
            { val: countdown.seconds, label: 'SEC', color: 'from-rose-500 to-red-600' },
          ].map((unit, i) => (
            <div key={i} className="text-center">
              <div className={`bg-gradient-to-br ${unit.color} rounded-xl px-3 py-2 font-mono text-xl sm:text-2xl font-bold tabular-nums shadow-lg`}>
                {formatNum(unit.val)}
              </div>
              <div className="text-[9px] text-slate-500 mt-1 tracking-widest">{unit.label}</div>
            </div>
          ))}
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-3 gap-2 mb-4">
          <div className="bg-slate-800/60 border border-cyan-500/20 rounded-xl p-2.5 text-center">
            <div className="text-xl font-bold text-cyan-400">33°F</div>
            <div className="text-[10px] text-slate-500">FORECAST</div>
          </div>
          <div className="bg-slate-800/60 border border-fuchsia-500/20 rounded-xl p-2.5 text-center">
            <div className="text-xl font-bold text-fuchsia-400">1M+</div>
            <div className="text-[10px] text-slate-500">PEOPLE</div>
          </div>
          <div className="bg-slate-800/60 border border-amber-500/20 rounded-xl p-2.5 text-center">
            <div className="text-xl font-bold text-amber-400">0</div>
            <div className="text-[10px] text-slate-500">BATHROOMS</div>
          </div>
        </div>

        {/* Mascot Tip Banner */}
        {showMascot && (
          <div className="relative bg-gradient-to-r from-orange-500/10 to-amber-500/10 border border-orange-500/20 rounded-2xl p-3 mb-4 flex items-center gap-3">
            <KumquatMascot mood="cold" size={50} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-orange-200">Pro tip from your citrus friend:</p>
              <p className="text-xs text-slate-400 truncate">Layer up like you're climbing Everest! 🧥</p>
            </div>
            <button onClick={() => setShowMascot(false)} className="text-slate-500 hover:text-white">×</button>
          </div>
        )}

        {/* Pro CTA */}
        <button 
          onClick={() => setShowProModal(true)}
          className="w-full mb-5 p-3 bg-gradient-to-r from-amber-500/5 to-orange-500/5 border border-amber-500/30 rounded-xl flex items-center justify-between hover:border-amber-500/50 transition-all group"
        >
          <div className="flex items-center gap-2">
            <span className="text-xl">⭐</span>
            <div className="text-left">
              <div className="font-bold text-amber-400 text-sm">Upgrade to PRO</div>
              <div className="text-[10px] text-slate-500">Bathroom maps • Exit routes • Offline PDF</div>
            </div>
          </div>
          <span className="text-amber-400 group-hover:translate-x-1 transition-transform">→</span>
        </button>

        {/* Navigation */}
        <div className="flex justify-between gap-1.5 mb-5 overflow-x-auto pb-1">
          <TabButton id="zones" icon="📍" label="Zones" active={activeTab === 'zones'} />
          <TabButton id="mistakes" icon="⚠️" label="Don'ts" active={activeTab === 'mistakes'} />
          <TabButton id="pack" icon="🎒" label="Pack" active={activeTab === 'pack'} />
          <TabButton id="survival" icon="🚽" label="Hacks" active={activeTab === 'survival'} />
          <TabButton id="timeline" icon="⏰" label="Time" active={activeTab === 'timeline'} />
        </div>

        {/* Content */}
        <div className="bg-slate-900/50 border border-slate-800/50 rounded-2xl p-4 mb-5">
          
          {/* Zones */}
          {activeTab === 'zones' && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-bold mb-1">Best Viewing Zones</h2>
                <p className="text-slate-500 text-xs mb-3">Where you stand = what you see</p>
                
                <div className="space-y-2.5">
                  {zones.map((zone) => (
                    <div key={zone.id} className={`relative bg-slate-800/40 rounded-xl p-3 border ${zone.recommended ? 'border-cyan-500/40' : 'border-slate-700/30'}`}>
                      {zone.recommended && (
                        <div className="absolute -top-2 right-3 px-2 py-0.5 bg-cyan-500 text-[9px] font-bold rounded-full">✓ BEST</div>
                      )}
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <h3 className="font-bold text-sm">{zone.name}</h3>
                          <div className="flex gap-0.5 mt-0.5">
                            {[...Array(5)].map((_, i) => (
                              <span key={i} className={`text-xs ${i < zone.rating ? 'text-amber-400' : 'text-slate-700'}`}>★</span>
                            ))}
                          </div>
                        </div>
                        <div className={`px-2 py-0.5 rounded-lg bg-gradient-to-r ${zone.color} text-[10px] font-bold`}>
                          {zone.fillTime}
                        </div>
                      </div>
                      <div className="grid grid-cols-3 gap-1 text-[10px] text-slate-400 mb-2">
                        <div>⏱ {zone.wait}</div>
                        <div>👁 {zone.view}</div>
                        <div>🚪 {zone.street}</div>
                      </div>
                      <p className="text-xs text-cyan-400/80">💡 {zone.tip}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Map */}
              <div>
                <h3 className="font-bold text-sm mb-2">Interactive Map</h3>
                <div className="relative bg-slate-800/40 rounded-xl h-56 overflow-hidden border border-slate-700/30">
                  {/* Grid lines */}
                  <svg className="absolute inset-0 w-full h-full opacity-10">
                    {[...Array(8)].map((_, i) => (
                      <React.Fragment key={i}>
                        <line x1="0" y1={`${i * 12.5}%`} x2="100%" y2={`${i * 12.5}%`} stroke="white" />
                        <line x1={`${i * 12.5}%`} y1="0" x2={`${i * 12.5}%`} y2="100%" stroke="white" />
                      </React.Fragment>
                    ))}
                  </svg>
                  
                  {/* Street labels */}
                  <div className="absolute left-1 top-[18%] text-[8px] text-slate-600">46th</div>
                  <div className="absolute left-1 top-[42%] text-[8px] text-slate-600">44th</div>
                  <div className="absolute left-1 top-[66%] text-[8px] text-slate-600">42nd</div>

                  {/* Markers */}
                  {mapMarkers.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => setSelectedMarker(selectedMarker?.id === m.id ? null : m)}
                      className={`absolute transform -translate-x-1/2 -translate-y-1/2 transition-all ${selectedMarker?.id === m.id ? 'scale-150 z-20' : 'hover:scale-125 z-10'}`}
                      style={{ left: `${m.x}%`, top: `${m.y}%` }}
                    >
                      <div className={`rounded-full border-2 border-white shadow-lg ${
                        m.type === 'ball' ? 'w-5 h-5 bg-gradient-to-br from-red-400 to-rose-600 animate-pulse' :
                        m.type === 'zone' ? 'w-4 h-4 bg-gradient-to-br from-blue-400 to-cyan-600' :
                        'w-3.5 h-3.5 bg-gradient-to-br from-green-400 to-emerald-600'
                      }`}>
                        {m.zone && <span className="text-[8px] font-bold flex items-center justify-center h-full">{m.zone}</span>}
                      </div>
                    </button>
                  ))}

                  {/* Info popup */}
                  {selectedMarker && (
                    <div className="absolute bottom-2 left-2 right-2 bg-slate-900/95 rounded-lg p-2.5 border border-slate-600 shadow-xl">
                      <div className="font-bold text-xs">{selectedMarker.label}</div>
                      <p className="text-[10px] text-slate-400">{selectedMarker.desc}</p>
                    </div>
                  )}
                </div>
                <div className="flex justify-center gap-4 mt-2 text-[10px] text-slate-500">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-500"></span> Ball</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-cyan-500"></span> Zones</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500"></span> Entry</span>
                </div>
              </div>
            </div>
          )}

          {/* Mistakes */}
          {activeTab === 'mistakes' && (
            <div>
              <h2 className="text-lg font-bold mb-1">Avoid These Mistakes</h2>
              <p className="text-slate-500 text-xs mb-3">Learn from those who suffered before you</p>
              
              <div className="space-y-2">
                {mistakes.map((m, i) => (
                  <div key={i} className={`flex items-start gap-3 p-3 rounded-xl border ${
                    m.severity === 'high' ? 'bg-red-500/5 border-red-500/20' :
                    m.severity === 'medium' ? 'bg-amber-500/5 border-amber-500/20' :
                    'bg-slate-800/30 border-slate-700/20'
                  }`}>
                    <span className="text-xl">{m.icon}</span>
                    <div>
                      <h3 className="font-bold text-sm text-red-300">{m.title}</h3>
                      <p className="text-xs text-slate-400">{m.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Packing */}
          {activeTab === 'pack' && (
            <div className="space-y-4">
              <div>
                <div className="flex justify-between items-center mb-1">
                  <h2 className="text-lg font-bold">What to Pack</h2>
                  <span className="text-xs text-slate-500">
                    {Object.values(checkedItems).filter(Boolean).length}/{bringItems.length}
                  </span>
                </div>
                <p className="text-slate-500 text-xs mb-3">Tap to check off items</p>
                
                <div className="space-y-1.5">
                  {bringItems.map((item, i) => {
                    const key = `bring-${i}`;
                    const checked = checkedItems[key];
                    return (
                      <label key={i} className={`flex items-center gap-2.5 p-2.5 rounded-xl cursor-pointer transition-all ${checked ? 'bg-green-500/10 border-green-500/20' : 'bg-slate-800/40 border-slate-700/20'} border`}>
                        <input
                          type="checkbox"
                          checked={checked || false}
                          onChange={() => toggleItem(key)}
                          className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-green-500 focus:ring-green-500"
                        />
                        <span className={`flex-1 text-xs ${checked ? 'line-through text-slate-500' : ''}`}>{item.name}</span>
                        {item.critical && !checked && (
                          <span className="text-[9px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded">!</span>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>

              <div>
                <h2 className="text-lg font-bold text-red-400 mb-1">Do NOT Bring</h2>
                <p className="text-slate-500 text-xs mb-3">Will get you turned away</p>
                <div className="grid grid-cols-2 gap-1.5">
                  {dontBring.map((item, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 bg-red-500/5 border border-red-500/10 rounded-lg">
                      <span className="text-red-500 text-sm">✕</span>
                      <div>
                        <div className="text-xs font-medium">{item.name}</div>
                        <div className="text-[9px] text-slate-600">{item.reason}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* CTA */}
              <div className="bg-gradient-to-r from-orange-500/10 to-amber-500/10 border border-orange-500/20 rounded-xl p-3 text-center">
                <p className="text-xs font-medium mb-2">Want a printable version?</p>
                <button 
                  onClick={() => setShowEmailModal(true)}
                  className="px-4 py-2 bg-gradient-to-r from-orange-500 to-amber-500 rounded-full text-xs font-bold"
                >
                  Get Free PDF 📋
                </button>
              </div>
            </div>
          )}

          {/* Survival Hacks */}
          {activeTab === 'survival' && (
            <div>
              <h2 className="text-lg font-bold mb-1">Survival Hacks</h2>
              <p className="text-slate-500 text-xs mb-3">The brutal truths + pro secrets</p>
              
              <div className="space-y-2">
                {survivalHacks.map((hack, i) => (
                  <div key={i} className={`p-3 rounded-xl border ${hack.pro ? 'bg-amber-500/5 border-amber-500/20' : 'bg-slate-800/40 border-slate-700/20'}`}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-lg">{hack.icon}</span>
                      <h3 className="font-bold text-sm flex-1">{hack.title}</h3>
                      {hack.pro && <ProBadge />}
                    </div>
                    <p className="text-xs text-slate-400">{hack.desc}</p>
                    {hack.pro && (
                      <button 
                        onClick={() => setShowProModal(true)}
                        className="mt-2 text-amber-400 text-[10px] font-medium"
                      >
                        Unlock with PRO →
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timeline */}
          {activeTab === 'timeline' && (
            <div>
              <h2 className="text-lg font-bold mb-1">Dec 31 Timeline</h2>
              <p className="text-slate-500 text-xs mb-3">Know when to arrive</p>
              
              <div className="relative">
                <div className="absolute left-3 top-0 bottom-0 w-0.5 bg-gradient-to-b from-cyan-500 via-purple-500 to-amber-500 rounded-full"></div>
                <div className="space-y-2">
                  {timeline.map((event, i) => (
                    <div key={i} className="relative pl-8">
                      <div className={`absolute left-1.5 w-3 h-3 rounded-full border-2 border-slate-900 ${
                        event.phase === 'finale' ? 'bg-amber-500 animate-pulse' :
                        event.phase === 'late' ? 'bg-purple-500' :
                        event.phase === 'mid' ? 'bg-fuchsia-500' : 'bg-cyan-500'
                      }`}></div>
                      <div className="bg-slate-800/40 rounded-xl p-2.5 border border-slate-700/20">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="font-mono text-cyan-400 text-xs font-bold">{event.time}</span>
                          <span className="font-bold text-sm">{event.event}</span>
                        </div>
                        <p className="text-[10px] text-slate-500">{event.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Cumquat Vibes Footer Promo */}
        <div className="bg-slate-800/30 rounded-2xl p-4 mb-4 border border-slate-700/20">
          <div className="flex items-center gap-3">
            <KumquatMascot mood="happy" size={45} />
            <div className="flex-1 min-w-0">
              <div className="text-[10px] text-slate-500">A project by</div>
              <div className="font-bold text-orange-400">Cumquat Vibes</div>
              <div className="text-[10px] text-slate-500">Human-made art for creative souls</div>
            </div>
            <a 
              href="https://cumquatvibes.com" 
              target="_blank" 
              rel="noopener noreferrer"
              className="px-3 py-1.5 bg-orange-500/20 border border-orange-500/30 rounded-full text-orange-400 text-xs font-medium hover:bg-orange-500/30 transition-all whitespace-nowrap"
            >
              Shop →
            </a>
          </div>
        </div>

        {/* Bottom CTA */}
        <div className="text-center space-y-3 pb-6">
          <button 
            onClick={() => setShowEmailModal(true)}
            className="px-6 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-full font-bold text-sm hover:opacity-90 transition-all shadow-lg shadow-cyan-500/25"
          >
            📧 Get Free Checklist
          </button>
          <p className="text-[10px] text-slate-600">
            Made with ❄️ by{' '}
            <a href="https://cumquatvibes.com" className="text-orange-400 hover:underline">Cumquat Vibes</a>
          </p>
        </div>

        {/* Crowd illustration at bottom */}
        <CrowdIllustration />
      </div>
    </div>
  );
}
