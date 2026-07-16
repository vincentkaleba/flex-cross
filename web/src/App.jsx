import React, { useState, useEffect, useCallback, useRef } from 'react'
import WebApp from '@twa-dev/sdk'
import {
  Home,
  Megaphone,
  Users,
  Search,
  ChevronDown,
  ChevronRight,
  Menu,
  Trophy,
  Globe,
  Hash,
  TrendingUp,
  UserCheck,
  Loader2,
  X,
  TrendingUp as StatsIcon
} from 'lucide-react'

const API_BASE = 'https://flexapi.167.233.223.42.nip.io'

// Language to flag emoji map
const LANG_FLAG = {
  fr: '🇫🇷', en: '🇬🇧', ar: '🇸🇦', ru: '🇷🇺',
  es: '🇪🇸', pt: '🇵🇹', de: '🇩🇪', it: '🇮🇹',
  tr: '🇹🇷', zh: '🇨🇳', hi: '🇮🇳', fa: '🇮🇷',
}

const formatNum = (n) => {
  if (!n && n !== 0) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return n.toString()
}

// ──────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────

const ChannelAvatar = ({ photo, title }) => {
  const [err, setErr] = useState(false)
  const letter = title?.charAt(0)?.toUpperCase() || 'C'
  const colors = ['#3a3a5c', '#1e3a4a', '#2d3a1e', '#3a1e2d', '#1a2e3a']
  const bg = colors[letter.charCodeAt(0) % colors.length]

  if (photo && !err) {
    return (
      <img
        src={photo}
        alt={title}
        className="channel-avatar"
        onError={() => setErr(true)}
      />
    )
  }
  return (
    <div className="channel-avatar channel-avatar--fallback" style={{ background: bg }}>
      {letter}
    </div>
  )
}

const StatBadge = ({ value, label, icon: Icon }) => (
  <div className="stat-badge">
    {Icon && <Icon size={14} className="stat-badge__icon" />}
    <span className="stat-badge__value">{value}</span>
    <span className="stat-badge__label">{label}</span>
  </div>
)

const ChannelCard = ({ channel }) => {
  const flag = LANG_FLAG[channel.language] || ''
  const url = channel.link || (channel.username ? `https://t.me/${channel.username}` : null)
  const isSponsored = channel.is_sponsored === true

  return (
    <div className={`channel-card ${isSponsored ? 'channel-card--sponsored' : ''}`}>
      <div className="channel-card__body">
        <ChannelAvatar photo={channel.photo} title={channel.title} />
        <div className="channel-card__info">
          <div className="channel-card__title-row">
            <div className="channel-card__title-group">
              <span className="channel-card__title">{channel.title}</span>
              {isSponsored && (
                <span className="channel-card__verified" title="Vérifié">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="8" fill="#0a84ff"/>
                    <path d="M4.5 8l2.5 2.5 4.5-4.5" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </span>
              )}
              {flag && <span className="channel-card__flag">{flag}</span>}
            </div>
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="channel-card__join"
                onClick={(e) => e.stopPropagation()}
              >
                REJOINDRE
              </a>
            )}
          </div>
          {isSponsored ? (
            <p className="channel-card__sponsored-label">Sponsorisé</p>
          ) : (
            <p className="channel-card__meta">
              Canal • {channel.members_formatted || formatNum(channel.members_count)} abonnés
            </p>
          )}
          {channel.about && (
            <p className="channel-card__desc">{channel.about}</p>
          )}
        </div>
      </div>
    </div>
  )
}

const CategoryCard = ({ category, isSelected, onClick }) => {
  const ICONS = {
    anime: '🐉', movies: '🎥', music: '🎵', other: '✨',
    series: '📺', manga: '📖', crypto: '₿', news: '🗞️',
    tech: '🚀', sport: '⚽', finance: '💰', art: '🎨',
    gaming: '🎮', politics: '🏛️', health: '🏥', education: '📚',
    travel: '✈️', fashion: '💃', food: '🍕', animals: '🐘',
  }
  const icon = ICONS[category.name?.toLowerCase()] || '#️⃣'

  return (
    <div
      className={`category-card ${isSelected ? 'category-card--active' : ''}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onClick()}
    >
      <div className="category-card__icon">{icon}</div>
      <div className="category-card__content">
        <h3 className="category-card__name">{category.name}</h3>
        <p className="category-card__meta">
          {formatNum(category.channels_count)} Canaux
        </p>
      </div>
    </div>
  )
}

const SectionHeader = ({ title, icon: Icon, onViewMore }) => (
  <div className="section-header">
    <div className="section-header__left">
      {Icon && <Icon size={20} className="section-header__icon" />}
      <h2 className="section-header__title">{title}</h2>
    </div>
    {onViewMore && (
      <button className="section-header__more" onClick={onViewMore}>
        VOIR PLUS <ChevronRight size={13} strokeWidth={3} />
      </button>
    )}
  </div>
)

const SkeletonCard = () => (
  <div className="skeleton-card">
    <div className="skeleton-card__avatar skeleton-pulse" />
    <div className="skeleton-card__body">
      <div className="skeleton-card__line skeleton-pulse" style={{ width: '60%' }} />
      <div className="skeleton-card__line skeleton-pulse" style={{ width: '40%', marginTop: 6 }} />
      <div className="skeleton-card__line skeleton-pulse" style={{ width: '90%', marginTop: 10 }} />
    </div>
  </div>
)

const ModalPage = ({ title, isOpen, onClose, children }) => {
  // Prevent background scrolling when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [isOpen])

  if (!isOpen) return null

  return (
    <div className={`modal-page ${isOpen ? 'modal-page--open' : ''}`}>
      <div className="modal-page__header">
        <h2 className="modal-page__title">{title}</h2>
      </div>
      <div className="modal-page__content">
        {children}
      </div>
      <div className="modal-page__footer">
        <button className="modal-page__close-bottom" onClick={onClose}>
          Fermer
        </button>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────
// Main App
// ──────────────────────────────────────────────

const TABS = [
  { id: 'all',      label: 'Hub',     icon: Home },
  { id: 'channels', label: 'Canaux',  icon: Megaphone, dropdown: true },
  { id: 'groups',   label: 'Groupes', icon: Users,     dropdown: true },
]

const App = () => {
  const [channels, setChannels]         = useState([])
  const [categories, setCategories]     = useState([])
  const [stats, setStats]               = useState(null)
  const [searchQuery, setSearchQuery]   = useState('')
  const [selectedTab, setSelectedTab]   = useState('all')
  const [selectedCat, setSelectedCat]   = useState(null)
  const [loading, setLoading]           = useState(true)
  const [loadingMore, setLoadingMore]   = useState(false)
  const [page, setPage]                 = useState(0)
  const [hasMore, setHasMore]           = useState(true)
  const [searchFocused, setSearchFocused] = useState(false)
  const [isMenuOpen, setIsMenuOpen]     = useState(false)
  const [activePage, setActivePage]     = useState(null)

  // ── Data Fetching ──────────────────────────
  const fetchAll = useCallback(async () => {
    setLoading(true)
    setPage(0)
    setHasMore(true)
    try {
      const [catRes, chanRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/categories`),
        fetch(`${API_BASE}/api/channels?sort=members_count&limit=20&offset=0`),
        fetch(`${API_BASE}/api/stats`),
      ])
      const [catData, chanData, statsData] = await Promise.all([
        catRes.json(), chanRes.json(), statsRes.json()
      ])
      setCategories(catData.categories || [])
      setChannels(chanData.channels || [])
      setHasMore(chanData.has_more || false)
      setStats(statsData)
    } catch (err) {
      console.error('Fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchChannels = useCallback(async (q = '', cat = null, offset = 0, append = false) => {
    if (append) setLoadingMore(true)
    else setLoading(true)
    
    try {
      const params = new URLSearchParams({ sort: 'members_count', limit: 20, offset: offset.toString() })
      if (q) params.set('q', q)
      if (cat) params.set('cat', cat)
      const res = await fetch(`${API_BASE}/api/channels?${params}`)
      const data = await res.json()
      
      if (append) {
        setChannels(prev => [...prev, ...(data.channels || [])])
      } else {
        setChannels(data.channels || [])
      }
      setHasMore(data.has_more || false)
    } catch (err) {
      console.error('Channels fetch error:', err)
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [])

  const fetchMore = useCallback(() => {
    if (loadingMore || !hasMore || loading) return
    const nextOffset = (page + 1) * 20
    setPage(prev => prev + 1)
    fetchChannels(searchQuery, selectedCat, nextOffset, true)
  }, [loadingMore, hasMore, loading, page, searchQuery, selectedCat, fetchChannels])

  const observerTarget = useRef(null)

  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !loading && !loadingMore) {
          fetchMore()
        }
      },
      { threshold: 0.1, rootMargin: '100px' }
    )

    if (observerTarget.current) {
      observer.observe(observerTarget.current)
    }

    return () => {
      if (observerTarget.current) {
        observer.unobserve(observerTarget.current)
      }
    }
  }, [fetchMore, hasMore, loading, loadingMore])

  useEffect(() => {
    WebApp.ready()
    WebApp.expand() // Ensure app takes full height
    fetchAll()
  }, [fetchAll])

  // ── Handlers ──────────────────────────────
  const handleSearch = (e) => {
    const q = e.target.value
    setSearchQuery(q)
    setSelectedCat(null)
    setPage(0)
    fetchChannels(q, null, 0, false)
  }

  const handleCatClick = (catName) => {
    const next = selectedCat === catName ? null : catName
    setSelectedCat(next)
    setSearchQuery('')
    setPage(0)
    fetchChannels('', next, 0, false)
  }

  const handleTabClick = (tabId) => {
    setSelectedTab(tabId)
    setSelectedCat(null)
    setSearchQuery('')
    setPage(0)
    fetchChannels('', null, 0, false)
  }

  const clearSearch = () => {
    setSearchQuery('')
    setSelectedCat(null)
    setPage(0)
    fetchChannels('', null, 0, false)
  }

  // ──────────────────────────────────────────
  return (
    <div className={`app ${isMenuOpen ? 'app--menu-open' : ''}`}>

      {/* ── Side Drawer ────────────────────── */}
      <div className={`drawer-overlay ${isMenuOpen ? 'drawer-overlay--active' : ''}`} onClick={() => setIsMenuOpen(false)} />
      <aside className={`drawer ${isMenuOpen ? 'drawer--active' : ''}`}>
        <div className="drawer__header">
          <div className="header__brand">
            <div className="header__logo">
              <div className="header__logo-diamond" />
            </div>
            <span className="header__name">Flex Hub</span>
          </div>
          <button className="drawer__close" onClick={() => setIsMenuOpen(false)}>
            <X size={20} />
          </button>
        </div>
        
        <nav className="drawer__nav">
          <div className="drawer__group">
            <p className="drawer__label">Menu</p>
            <a 
              href="https://t.me/FlexAds_robot?start=" 
              target="_blank" 
              rel="noopener noreferrer" 
              className="drawer__item" 
              onClick={() => setIsMenuOpen(false)}
            >
              <Megaphone size={18} aria-hidden="true" /> Ajouter mon canal
            </a>
            <button className="drawer__item" onClick={() => {
              setIsMenuOpen(false);
              alert("Pour promouvoir vos canaux, veuillez contacter le support pour le moment.");
              setActivePage('support');
            }}>
              <StatsIcon size={18} aria-hidden="true" /> Publicité
            </button>
            <button className="drawer__item" onClick={() => { setIsMenuOpen(false); window.scrollTo(0,0); }}>
              <Trophy size={18} aria-hidden="true" /> Top 100
            </button>
          </div>

          <div className="drawer__group">
            <p className="drawer__label">Services</p>
            <button className="drawer__item" onClick={() => { setIsMenuOpen(false); setActivePage('terms'); }}>
              <Hash size={18} aria-hidden="true" /> Conditions
            </button>
            <button className="drawer__item" onClick={() => { setIsMenuOpen(false); setActivePage('privacy'); }}>
              <UserCheck size={18} aria-hidden="true" /> Confidentialité
            </button>
            <button className="drawer__item" onClick={() => { setIsMenuOpen(false); setActivePage('support'); }}>
              <Users size={18} aria-hidden="true" /> Support
            </button>
          </div>

          <div className="drawer__group-bottom">
            <p className="drawer__copy">Version 2.4.0 (Stable)</p>
          </div>
        </nav>
      </aside>

      {/* ── Sticky Header ───────────────────── */}
      <header className="header">
        <div className="header__top">
          <div className="header__brand">
            <div className="header__logo" aria-hidden="true">
              <div className="header__logo-diamond" />
            </div>
            <span className="header__name">Flex Hub</span>
          </div>
          <button 
            className="header__menu" 
            aria-label="Menu" 
            onClick={() => setIsMenuOpen(true)}
          >
            <Menu size={22} />
          </button>
        </div>

        {/* Navigation tabs */}
        <nav className="nav-tabs" aria-label="Navigation">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              className={`nav-tab ${selectedTab === tab.id ? 'nav-tab--active' : ''}`}
              onClick={() => handleTabClick(tab.id)}
            >
              <tab.icon size={13} strokeWidth={2.5} aria-hidden="true" />
              {tab.label}
              {tab.dropdown && <ChevronDown size={11} strokeWidth={3} aria-hidden="true" />}
            </button>
          ))}
        </nav>
      </header>

      <main className="main">

        {/* ── Hero Section ────────────────────── */}
        <section className="hero">
          <h1 className="hero__title">
            Flex Hub
            <span className="hero__subtitle">
              {' '}Explorez les meilleurs canaux,<br />groupes et bots Telegram&nbsp;!
            </span>
          </h1>
          <p className="hero__desc">
            Recherchez librement, catégorisez vos découvertes et notez vos favoris au sommet&nbsp;!
          </p>

          {/* Real stats strip */}
          {stats && (
            <div className="stats-strip">
              <StatBadge icon={Megaphone} value={stats.total_channels_formatted} label="Canaux" />
              <div className="stats-strip__divider" />
              <StatBadge icon={UserCheck} value={stats.total_users_formatted} label="Utilisateurs" />
              <div className="stats-strip__divider" />
              <StatBadge icon={StatsIcon} value={stats.total_members_formatted} label="Abonnés" />
            </div>
          )}
        </section>

        {/* ── Search Bar ──────────────────────── */}
        <div className="search-bar" id="search-section">
          <div className={`search-bar__inner ${searchFocused ? 'search-bar__inner--focused' : ''}`}>
            <Search size={18} className="search-bar__icon" strokeWidth={2.5} />
            <input
              id="search-input"
              type="text"
              placeholder="Rechercher des canaux…"
              className="search-bar__input"
              value={searchQuery}
              onChange={handleSearch}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setSearchFocused(false)}
              autoComplete="off"
            />
            {searchQuery && (
              <button className="search-bar__clear" onClick={clearSearch} aria-label="Effacer">
                <X size={15} />
              </button>
            )}
          </div>
          <button className="search-bar__filter" aria-label="Filtres">
            <ChevronDown size={18} strokeWidth={2.5} />
          </button>
        </div>

        {/* ── Content Sections ────────────────── */}
        <div className="sections">

          {/* 1 ─ Categories Slider */}
          {!searchQuery && (
            <section className="section" id="section-categories">
              <SectionHeader
                title="Parcourir par catégorie"
              />
              <div className="category-list">
                {loading && categories.length === 0
                  ? Array(3).fill(0).map((_, i) => (
                    <div key={i} className="skeleton-category skeleton-pulse" />
                  ))
                  : categories.map((cat) => (
                    <CategoryCard
                      key={cat.name}
                      category={cat}
                      isSelected={selectedCat === cat.name}
                      onClick={() => handleCatClick(cat.name)}
                    />
                  ))
                }
              </div>
            </section>
          )}

          {/* 2 ─ Top Channels */}
          <section className="section" id="section-top100">
            <SectionHeader
              title={selectedCat ? `Catégorie : ${selectedCat}` : searchQuery ? `Résultats pour "${searchQuery}"` : "Top Flex Hub"}
              icon={!searchQuery && !selectedCat ? Trophy : undefined}
            />

            <div className="channel-list">
              {loading
                ? Array(4).fill(0).map((_, i) => <SkeletonCard key={i} />)
                : channels.length === 0
                  ? (
                    <div className="empty-state">
                      <Globe size={40} className="empty-state__icon" />
                      <p>Aucun canal trouvé</p>
                    </div>
                  )
                  : channels.map((ch) => (
                    <ChannelCard key={`${ch.is_sponsored ? 'sp-' : ''}${ch.channel_id}`} channel={ch} />
                  ))
              }
              {loadingMore && (
                <div className="loading-more">
                  <Loader2 size={24} className="animate-spin text-blue-500" />
                  <span>Chargement des canaux suivants...</span>
                </div>
              )}
              {/* Sentinel for IntersectionObserver */}
              <div ref={observerTarget} style={{ height: '20px', width: '100%' }} />
            </div>
          </section>

        </div>
      </main>

      {/* ── Footer ──────────────────────────── */}
      <footer className="footer">
        <div className="footer__links">
          <span onClick={() => setActivePage('terms')}>Conditions</span>
          <span onClick={() => setActivePage('privacy')}>Confidentialité</span>
          <span onClick={() => setActivePage('support')}>Support</span>
        </div>
        <p className="footer__copy">© 2026 Flex Hub • Tous droits réservés</p>
      </footer>

      {/* ── Modals / Fullscreen Pages ──────── */}
      <ModalPage title="Conditions d'utilisation" isOpen={activePage === 'terms'} onClose={() => setActivePage(null)}>
        <div className="text-content">
          <p>Bienvenue sur <strong>Flex Hub</strong>. En naviguant et en utilisant notre service, vous acceptez les présentes conditions d'utilisation.</p>
          
          <h3>1. Utilisation du Service</h3>
          <p>Le Hub est un annuaire public visant à faciliter la découverte de canaux, groupes et bots Telegram. Les contenus indexés restent la propriété exclusive de leurs administrateurs respectifs.</p>
          
          <h3>2. Contenus Inappropriés</h3>
          <p>Afin de maintenir une communauté saine, tous les canaux indexés doivent respecter les Conditions de Service de Telegram. Nous nous réservons le droit exclusif de retirer ou bannir n'importe quel canal du Hub si nous jugeons son contenu inapproprié (violence, fraude, nudité, etc).</p>
          
          <h3>3. Promotions et Sponsoring</h3>
          <p>Certains canaux peuvent apparaître mis en avant avec l'étiquette "Sponsorisé". Ces placements sont des accords publicitaires établis avec la plateforme ou notre réseau, dans le but de soutenir le développement de nos services.</p>
          
          <h3>4. Responsabilité</h3>
          <p>Flex Hub ne peut être tenu responsable du contenu publié dans les canaux externes vers lesquels il redirige. Vous êtes seul responsable des canaux que vous choisissez de rejoindre.</p>
        </div>
      </ModalPage>

      <ModalPage title="Confidentialité" isOpen={activePage === 'privacy'} onClose={() => setActivePage(null)}>
        <div className="text-content">
          <p>La protection de vos données est une priorité pour nous.</p>
          
          <h3>1. Données Utilisateur</h3>
          <p>Dans le cadre de l'utilisation de cette interface "Mini-App" Telegram, nous n'extrayons, ne collectons, ni ne stockons aucune information personnelle vous concernant (pas de numéro de téléphone, pas d'identification privée).</p>
          
          <h3>2. Données Publiques des Canaux</h3>
          <p>Nous n'indexons que des informations strictement publiques relatives aux canaux Telegram (le titre du canal, son @nom_d_utilisateur, la description publique, la photo de profil, et le nombre d'abonnés). Ces données sont synchronisées via l'API Telegram de nos bots administrateurs.</p>
          
          <h3>3. Suppression de vos données</h3>
          <p>Si vous êtes propriétaire d'un canal et souhaitez qu'il n'apparaisse plus dans le Flex Hub, il vous suffit de retirer l'un de nos bots de votre canal, ou d'utiliser le menu de configuration de notre bot pour supprimer manuellement le canal. Sa disparition du Hub sera immédiate à la prochaine synchronisation.</p>
        </div>
      </ModalPage>

      <ModalPage title="Support & Assistance" isOpen={activePage === 'support'} onClose={() => setActivePage(null)}>
        <div className="support-content">
          <Users size={56} className="support-icon" />
          <h3 className="support-hi">Besoin d'aide ?</h3>
          <p className="support-desc">
            Vous avez une question, vous rencontrez un problème technique, ou vous souhaitez nous signaler un comportement suspect concernant un bot ou un canal ?
          </p>
          <p className="support-desc">
            Notre équipe d'assistance est à votre disposition via notre canal/bot de support officiel :
          </p>
          
          <a href="https://t.me/v_compress_support" target="_blank" rel="noopener noreferrer" className="support-btn">
            Contacter le Support
          </a>
          
          <p className="support-note">Assurez-vous de décrire brièvement votre situation dès votre premier message pour un traitement plus rapide !</p>
        </div>
      </ModalPage>

    </div>
  )
}

export default App
