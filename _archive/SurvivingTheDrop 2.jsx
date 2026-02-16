import React, { useState, useEffect } from 'react';

export default function SurvivingTheDrop() {
  const [activeTab, setActiveTab] = useState('map');
  const [countdown, setCountdown] = useState({ days: 0, hours: 0, minutes: 0, seconds: 0 });
  const [selectedMarker, setSelectedMarker] = useState(null);

  // Countdown to NYE 2026
  useEffect(() => {
    const targetDate = new Date('2026-01-01T00:00:00-05:00');
    
    const updateCountdown = () => {
      const now = new Date();
      const diff = targetDate - now;
      
      if (diff > 0) {
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((diff % (1000 * 60)) / 1000);
        setCountdown({ days, hours, minutes, seconds });
      }
    };
    
    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, []);

  const formatNumber = (num) => String(num).padStart(2, '0');

  const CountdownDisplay = ({ value, label }) => (
    <div className="flex flex-col items-center">
      <div className="bg-slate-800/80 rounded-lg px-2 py-1 font-mono text-xl font-bold text-white">
        {formatNumber(value)}
      </div>
      <span className="text-[10px] text-slate-400 mt-1">{label}</span>
    </div>
  );

  const mapMarkers = [
    { id: 'ball', x: 50, y: 65, type: 'ball', label: 'The Ball', desc: 'One Times Square - The iconic ball drops at midnight from 141 feet above.' },
    { id: 'pen1', x: 35, y: 55, type: 'pen', label: 'Viewing Pen A', desc: 'First to fill. Best view but longest wait (12+ hours). Enter from 43rd St.' },
    { id: 'pen2', x: 45, y: 45, type: 'pen', label: 'Viewing Pen B', desc: 'Second tier viewing. Still great visibility. Enter from 44th St.' },
    { id: 'pen3', x: 55, y: 35, type: 'pen', label: 'Viewing Pen C', desc: 'Good view of screens. Less crowded. Enter from 45th St.' },
    { id: 'pen4', x: 42, y: 25, type: 'pen', label: 'Viewing Pen D', desc: 'Family-friendly section. Enter from 46th St.' },
    { id: 'entry1', x: 25, y: 70, type: 'entry', label: 'Entry Point 1', desc: '42nd St & 7th Ave - Main security checkpoint. Expect 1-2 hour wait after 3 PM.' },
    { id: 'entry2', x: 65, y: 50, type: 'entry', label: 'Entry Point 2', desc: '44th St & Broadway - Less crowded alternative. Opens at 3 PM.' },
    { id: 'entry3', x: 30, y: 20, type: 'entry', label: 'Entry Point 3', desc: '47th St & 7th Ave - Northern entry. Good for Pens C & D.' },
  ];

  const timelineEvents = [
    { time: '11:00 AM', event: 'Streets Begin Closing', desc: 'Broadway and 7th Ave start closing to traffic. Barriers go up.' },
    { time: '1:00 PM', event: 'Viewing Pens Open', desc: 'Security checkpoints activate. First pens begin filling from south to north.' },
    { time: '3:00 PM', event: 'Prime Arrival Window Ends', desc: 'After this, expect significant wait times at security. Front pens likely full.' },
    { time: '6:00 PM', event: 'Live Performances Begin', desc: 'Musical acts start on the main stage. Energy picks up significantly.' },
    { time: '8:00 PM', event: 'Hourly Countdown Tests', desc: 'Ball lighting tests begin. Practice countdowns every hour.' },
    { time: '10:30 PM', event: 'Final Countdown Prep', desc: 'Last performances wrap up. Crowd energy reaches peak.' },
    { time: '11:59 PM', event: '60-Second Countdown', desc: 'The ball begins its descent. This is what you came for.' },
    { time: '12:00 AM', event: 'HAPPY NEW YEAR!', desc: 'Confetti drops, fireworks explode, strangers become friends. 🎉' },
  ];

  const survivalItems = [
    { category: 'Warmth', items: [
      { name: 'Hand/toe warmers (10+ pairs)', critical: true },
      { name: 'Thermal base layers', critical: true },
      { name: 'Insulated waterproof boots', critical: true },
      { name: 'Multiple pairs of warm socks', critical: false },
      { name: 'Balaclava or ski mask', critical: false },
      { name: 'Insulated gloves (touchscreen compatible)', critical: true },
    ]},
    { category: 'Sustenance', items: [
      { name: 'High-calorie snacks (protein bars, nuts)', critical: true },
      { name: 'Bottled water (freeze half overnight)', critical: true },
      { name: 'Thermos with hot beverage', critical: false },
      { name: 'Hard candy for energy', critical: false },
    ]},
    { category: 'Comfort', items: [
      { name: 'Adult diapers (seriously)', critical: true },
      { name: 'Portable phone charger (fully charged)', critical: true },
      { name: 'Small foldable seat cushion', critical: false },
      { name: 'Entertainment (downloaded content)', critical: false },
    ]},
    { category: 'Safety', items: [
      { name: 'Photo ID', critical: true },
      { name: 'Fully charged phone', critical: true },
      { name: 'Cash (small bills)', critical: false },
      { name: 'Meeting point plan with group', critical: true },
    ]},
  ];

  const proTips = [
    { title: 'The Bathroom Reality', tip: 'There are NO public restrooms in the viewing pens. None. Zero. This is not a drill. Plan accordingly or wear protection.', icon: '🚽' },
    { title: 'Once You\'re In, You\'re In', tip: 'Leave the pen = lose your spot. No re-entry. No exceptions. Commit fully or don\'t go at all.', icon: '🔒' },
    { title: 'Arrive Absurdly Early', tip: '1 PM is "on time." Before noon is smart. 3 PM means you\'re watching on screens from 47th street.', icon: '⏰' },
    { title: 'Dress for Survival', tip: 'You will stand still for 10+ hours in freezing temps. Dress like you\'re summiting Everest, not going to a party.', icon: '🧥' },
    { title: 'Backpacks Are Banned', tip: 'Large bags, backpacks, and umbrellas are prohibited. Use a small clear bag or stuff pockets.', icon: '🎒' },
    { title: 'Cell Service Dies', tip: 'With 1M+ people, networks collapse. Download offline content. Set a physical meeting point with your group.', icon: '📱' },
    { title: 'The Exit Chaos', tip: 'After midnight, controlled release by pen. Could take 1-2 hours to exit. Subways are packed until 2 AM.', icon: '🚇' },
    { title: 'Is It Worth It?', tip: 'Honestly? Once is enough for most people. It\'s a bucket list item, not an annual tradition. Manage expectations.', icon: '🤔' },
  ];

  const [checkedItems, setCheckedItems] = useState({});
  
  const toggleItem = (category, itemName) => {
    const key = `${category}-${itemName}`;
    setCheckedItems(prev => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 text-white font-sans">
      {/* Ambient glow effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-500/20 rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl"></div>
      </div>

      <div className="relative z-10 max-w-4xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-block px-4 py-1 bg-yellow-500/20 border border-yellow-500/50 rounded-full text-yellow-400 text-sm font-medium mb-4">
            NYE 2026 • NYC
          </div>
          <h1 className="text-5xl md:text-6xl font-black tracking-tight mb-3" style={{ fontFamily: 'system-ui', textShadow: '0 0 40px rgba(168, 85, 247, 0.4)' }}>
            SURVIVING<br />THE DROP
          </h1>
          <p className="text-slate-400 text-lg max-w-xl mx-auto">
            The ultimate tactical guide for the 2026 Times Square New Year's Eve Countdown.
          </p>
        </div>

        {/* Info Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {/* Weather Card */}
          <div className="bg-slate-800/50 backdrop-blur border border-cyan-500/50 rounded-2xl p-5">
            <div className="flex justify-between items-start mb-3">
              <div>
                <div className="flex items-center gap-2">
                  <CountdownDisplay value={countdown.days} label="DAYS" />
                  <CountdownDisplay value={countdown.hours} label="HRS" />
                </div>
              </div>
              <span className="text-3xl">🌨️</span>
            </div>
            <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">Forecast Dec 31</div>
            <div className="text-4xl font-bold">33°F <span className="text-lg text-slate-400">/ 25°F</span></div>
            <div className="text-cyan-400 text-sm mt-1">❄️ Snow Showers</div>
            <div className="border-t border-slate-700 mt-4 pt-4">
              <div className="text-sm">
                <span className="font-semibold">Advisory:</span> Bitterly cold. Dress in heavy layers. 25% chance of snow accumulation.
              </div>
            </div>
          </div>

          {/* Crowd Card */}
          <div className="bg-slate-800/50 backdrop-blur border border-fuchsia-500/50 rounded-2xl p-5">
            <div className="flex justify-between items-start mb-3">
              <div className="flex items-center gap-2">
                <CountdownDisplay value={countdown.minutes} label="MIN" />
                <CountdownDisplay value={countdown.seconds} label="SEC" />
              </div>
              <span className="text-3xl">👥</span>
            </div>
            <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">Crowd Status</div>
            <div className="text-4xl font-bold text-fuchsia-400">Extreme</div>
            <div className="text-fuchsia-300 text-sm mt-1">1 Million+ Expected</div>
            <div className="border-t border-slate-700 mt-4 pt-4">
              <div className="text-sm">
                <span className="font-semibold">Strategy:</span> Arrive by <span className="text-fuchsia-400 font-bold">1:00 PM</span> to secure a view. Pens fill north from 43rd St.
              </div>
            </div>
          </div>

          {/* Bathroom Card */}
          <div className="bg-slate-800/50 backdrop-blur border border-yellow-500/50 rounded-2xl p-5">
            <div className="flex justify-between items-start mb-3">
              <div className="bg-red-500/20 text-red-400 px-2 py-1 rounded text-xs font-bold">⚠️ CRITICAL</div>
              <span className="text-3xl">🚫</span>
            </div>
            <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">Bathroom Access</div>
            <div className="text-4xl font-bold text-yellow-400">Zero</div>
            <div className="text-yellow-300 text-sm mt-1">No Public Restrooms</div>
            <div className="border-t border-slate-700 mt-4 pt-4">
              <div className="text-sm">
                <span className="font-semibold">Reality Check:</span> Once you are in a viewing pen, you cannot leave and return. Plan accordingly.
              </div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex flex-wrap justify-center gap-2 mb-6">
          <button
            onClick={() => setActiveTab('map')}
            className={`flex items-center gap-2 px-5 py-3 rounded-full font-medium transition-all ${
              activeTab === 'map'
                ? 'bg-cyan-500 text-white shadow-lg shadow-cyan-500/30'
                : 'bg-slate-800/70 text-slate-300 hover:bg-slate-700'
            }`}
          >
            <span>📍</span> Map & Entry
          </button>
          <button
            onClick={() => setActiveTab('timeline')}
            className={`flex items-center gap-2 px-5 py-3 rounded-full font-medium transition-all ${
              activeTab === 'timeline'
                ? 'bg-cyan-500 text-white shadow-lg shadow-cyan-500/30'
                : 'bg-slate-800/70 text-slate-300 hover:bg-slate-700'
            }`}
          >
            <span>🕐</span> Timeline
          </button>
          <button
            onClick={() => setActiveTab('survival')}
            className={`flex items-center gap-2 px-5 py-3 rounded-full font-medium transition-all ${
              activeTab === 'survival'
                ? 'bg-cyan-500 text-white shadow-lg shadow-cyan-500/30'
                : 'bg-slate-800/70 text-slate-300 hover:bg-slate-700'
            }`}
          >
            <span>🎒</span> Survival Kit
          </button>
          <button
            onClick={() => setActiveTab('tips')}
            className={`flex items-center gap-2 px-5 py-3 rounded-full font-medium transition-all ${
              activeTab === 'tips'
                ? 'bg-cyan-500 text-white shadow-lg shadow-cyan-500/30'
                : 'bg-slate-800/70 text-slate-300 hover:bg-slate-700'
            }`}
          >
            <span>💡</span> Pro Tips
          </button>
        </div>

        {/* Content Area */}
        <div className="bg-slate-900/70 backdrop-blur border border-slate-700/50 rounded-2xl p-6 min-h-[400px]">
          
          {/* Map Tab */}
          {activeTab === 'map' && (
            <div>
              <div className="relative bg-slate-800/50 rounded-xl h-80 mb-4 overflow-hidden">
                {/* Simplified map grid */}
                <div className="absolute inset-0 opacity-20">
                  {[...Array(10)].map((_, i) => (
                    <div key={`h-${i}`} className="absolute w-full h-px bg-slate-500" style={{ top: `${i * 10}%` }}></div>
                  ))}
                  {[...Array(10)].map((_, i) => (
                    <div key={`v-${i}`} className="absolute h-full w-px bg-slate-500" style={{ left: `${i * 10}%` }}></div>
                  ))}
                </div>
                
                {/* Street labels */}
                <div className="absolute top-[15%] left-2 text-xs text-slate-500 font-medium">47th St</div>
                <div className="absolute top-[35%] left-2 text-xs text-slate-500 font-medium">45th St</div>
                <div className="absolute top-[55%] left-2 text-xs text-slate-500 font-medium">43rd St</div>
                <div className="absolute top-[75%] left-2 text-xs text-slate-500 font-medium">42nd St</div>
                <div className="absolute bottom-2 left-[30%] text-xs text-slate-500 font-medium">7th Ave</div>
                <div className="absolute bottom-2 right-[30%] text-xs text-slate-500 font-medium">Broadway</div>

                {/* Map markers */}
                {mapMarkers.map((marker) => (
                  <button
                    key={marker.id}
                    onClick={() => setSelectedMarker(selectedMarker?.id === marker.id ? null : marker)}
                    className={`absolute transform -translate-x-1/2 -translate-y-1/2 transition-all duration-200 ${
                      selectedMarker?.id === marker.id ? 'scale-125 z-20' : 'hover:scale-110 z-10'
                    }`}
                    style={{ left: `${marker.x}%`, top: `${marker.y}%` }}
                  >
                    <div className={`w-4 h-4 rounded-full border-2 border-white shadow-lg ${
                      marker.type === 'ball' ? 'bg-red-500 w-6 h-6 animate-pulse' :
                      marker.type === 'pen' ? 'bg-blue-500' :
                      'bg-green-500'
                    }`}></div>
                  </button>
                ))}

                {/* Selected marker info */}
                {selectedMarker && (
                  <div className="absolute bottom-4 left-4 right-4 bg-slate-900/95 backdrop-blur rounded-lg p-4 border border-slate-600">
                    <div className="flex items-center gap-2 mb-2">
                      <div className={`w-3 h-3 rounded-full ${
                        selectedMarker.type === 'ball' ? 'bg-red-500' :
                        selectedMarker.type === 'pen' ? 'bg-blue-500' :
                        'bg-green-500'
                      }`}></div>
                      <span className="font-bold">{selectedMarker.label}</span>
                    </div>
                    <p className="text-sm text-slate-300">{selectedMarker.desc}</p>
                  </div>
                )}
              </div>

              {/* Map Legend */}
              <div className="bg-slate-800/50 rounded-xl p-4">
                <h3 className="font-bold mb-3">Map Legend</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-red-500"></div>
                    <span>The Ball (One Times Square)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                    <span>Viewing Pens (Fill S to N)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-green-500"></div>
                    <span>Security Entry Points</span>
                  </div>
                </div>
                <p className="text-xs text-slate-400 mt-3 italic">Click markers for details.</p>
              </div>
            </div>
          )}

          {/* Timeline Tab */}
          {activeTab === 'timeline' && (
            <div>
              <h3 className="text-xl font-bold mb-4">December 31st Timeline</h3>
              <div className="relative">
                <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gradient-to-b from-cyan-500 via-fuchsia-500 to-yellow-500"></div>
                <div className="space-y-4">
                  {timelineEvents.map((event, index) => (
                    <div key={index} className="relative pl-10">
                      <div className={`absolute left-2 w-4 h-4 rounded-full border-2 border-white ${
                        index === timelineEvents.length - 1 ? 'bg-yellow-500 animate-pulse' : 'bg-slate-700'
                      }`}></div>
                      <div className="bg-slate-800/50 rounded-xl p-4 hover:bg-slate-800/70 transition-colors">
                        <div className="flex items-center gap-3 mb-1">
                          <span className="text-cyan-400 font-mono font-bold">{event.time}</span>
                          <span className="font-semibold">{event.event}</span>
                        </div>
                        <p className="text-sm text-slate-400">{event.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Survival Kit Tab */}
          {activeTab === 'survival' && (
            <div>
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-xl font-bold">Survival Kit Checklist</h3>
                <div className="text-sm text-slate-400">
                  {Object.values(checkedItems).filter(Boolean).length} / {survivalItems.flatMap(c => c.items).length} packed
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                {survivalItems.map((category) => (
                  <div key={category.category} className="bg-slate-800/50 rounded-xl p-4">
                    <h4 className="font-bold text-cyan-400 mb-3">{category.category}</h4>
                    <div className="space-y-2">
                      {category.items.map((item) => {
                        const key = `${category.category}-${item.name}`;
                        const isChecked = checkedItems[key];
                        return (
                          <label key={item.name} className="flex items-center gap-3 cursor-pointer group">
                            <input
                              type="checkbox"
                              checked={isChecked || false}
                              onChange={() => toggleItem(category.category, item.name)}
                              className="w-4 h-4 rounded border-slate-500 bg-slate-700 text-cyan-500 focus:ring-cyan-500"
                            />
                            <span className={`text-sm flex-1 ${isChecked ? 'line-through text-slate-500' : ''}`}>
                              {item.name}
                            </span>
                            {item.critical && !isChecked && (
                              <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded">CRITICAL</span>
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pro Tips Tab */}
          {activeTab === 'tips' && (
            <div>
              <h3 className="text-xl font-bold mb-4">Pro Tips from Veterans</h3>
              <div className="grid md:grid-cols-2 gap-4">
                {proTips.map((tip, index) => (
                  <div key={index} className="bg-slate-800/50 rounded-xl p-4 hover:bg-slate-800/70 transition-colors">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-2xl">{tip.icon}</span>
                      <h4 className="font-bold text-yellow-400">{tip.title}</h4>
                    </div>
                    <p className="text-sm text-slate-300">{tip.tip}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="text-center mt-6 text-xs text-slate-500">
          <p>Stay safe. Stay warm. Happy New Year! 🎆</p>
        </div>
      </div>
    </div>
  );
}
