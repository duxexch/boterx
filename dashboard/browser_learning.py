"""
VEX Browser Learning Engine
Observes actions, builds patterns, learns from success/failure.
"""
import re, time, json
from urllib.parse import urlparse
from datetime import datetime


def _domain_from_url(url):
    """Extract domain from URL."""
    try:
        return urlparse(url).netloc.lower().replace('www.', '')
    except Exception:
        return ''


class LearningEngine:
    """Learns from browser interactions and builds knowledge."""

    def __init__(self):
        self._pending_actions = {}  # instance_id -> list of actions in progress

    def record_action(self, instance_id, url, action_type, selector='',
                      value='', success=True, error='', duration_ms=0, page=None):
        """Record a browser action and learn from it."""
        from browser_knowledge import log_action, reinforce, learn

        domain = _domain_from_url(url)
        if not domain:
            return

        # Log the action
        log_action(
            instance_id, domain, action_type, selector, value,
            success, error, duration_ms, page_url=url
        )

        # Reinforce or penalize selector knowledge
        if selector and action_type in ('click', 'type', 'fill'):
            ktype = 'selector'
            if success:
                reinforce(domain, ktype, selector, success=True)
            else:
                reinforce(domain, ktype, selector, success=False)

        # Learn from successful navigation
        if action_type == 'navigate' and success:
            learn(domain, 'url_pattern', url, url, confidence=0.6)

        # Learn from errors
        if not success and error:
            self._learn_from_error(domain, action_type, selector, error)

    def _learn_from_error(self, domain, action_type, selector, error):
        """Extract lessons from error messages."""
        from browser_knowledge import learn

        error_lower = error.lower()

        # Timeout — selector might be wrong
        if 'timeout' in error_lower or 'waiting' in error_lower:
            if selector:
                learn(domain, 'unreliable_selector', selector, error, confidence=0.3)

        # Not found — selector definitely wrong
        if 'not found' in error_lower or 'strict mode' in error_lower:
            if selector:
                learn(domain, 'dead_selector', selector, error, confidence=0.4)

        # Navigation error — site might block
        if 'navigation' in error_lower and 'blocked' in error_lower:
            learn(domain, 'site_block', 'navigation', error, confidence=0.5)

    def analyze_page(self, page, domain):
        """Analyze a page and extract useful selectors/patterns."""
        from browser_knowledge import learn

        if not page:
            return {}

        findings = {}

        try:
            # Find login-related elements
            login_selectors = page.evaluate('''() => {
                const results = [];
                // Buttons
                document.querySelectorAll('button, input[type="submit"], a').forEach(el => {
                    const text = (el.textContent || '').toLowerCase().trim();
                    const type = el.getAttribute('type') || '';
                    const name = el.getAttribute('name') || '';
                    const id = el.id || '';
                    const testid = el.getAttribute('data-testid') || '';
                    if (text.match(/login|sign.?in|log.?in|دخول|تسجيل الدخول/i)) {
                        results.push({
                            selector: testid ? `[data-testid="${testid}"]` :
                                      id ? `#${id}` :
                                      name ? `button[name="${name}"]` : null,
                            type: 'login_button',
                            text: text.substring(0, 50)
                        });
                    }
                });
                // Inputs
                document.querySelectorAll('input').forEach(el => {
                    const type = el.type || '';
                    const name = el.name || '';
                    const id = el.id || '';
                    const placeholder = el.placeholder || '';
                    const autocomplete = el.autocomplete || '';
                    if (type === 'password' || autocomplete === 'current-password') {
                        results.push({
                            selector: id ? `#${id}` : name ? `[name="${name}"]` : null,
                            type: 'password_field',
                            placeholder: placeholder
                        });
                    }
                    if (type === 'email' || type === 'text' && (name.match(/user|email|phone|login/i) || placeholder.match(/email|phone|user/i))) {
                        results.push({
                            selector: id ? `#${id}` : name ? `[name="${name}"]` : null,
                            type: 'username_field',
                            placeholder: placeholder
                        });
                    }
                });
                return results.filter(r => r.selector);
            }''')

            if login_selectors:
                findings['login_elements'] = login_selectors
                for el in login_selectors:
                    learn(domain, 'selector', el['selector'], el['type'], confidence=0.7)

            # Find forms
            forms = page.evaluate('''() => {
                const results = [];
                document.querySelectorAll('form').forEach((form, i) => {
                    const action = form.action || '';
                    const method = form.method || 'GET';
                    const fields = [];
                    form.querySelectorAll('input, textarea, select').forEach(el => {
                        fields.push({
                            tag: el.tagName.toLowerCase(),
                            type: el.type || '',
                            name: el.name || '',
                            id: el.id || '',
                            required: el.required
                        });
                    });
                    results.push({
                        index: i,
                        action: action,
                        method: method,
                        field_count: fields.length,
                        fields: fields
                    });
                });
                return results;
            }''')

            if forms:
                findings['forms'] = forms
                for form in forms:
                    learn(domain, 'form_pattern', f"form_{form['index']}", json.dumps(form), confidence=0.6)

            # Find navigation links
            nav_links = page.evaluate('''() => {
                const links = [];
                document.querySelectorAll('nav a, [role="navigation"] a, .sidebar a, .menu a').forEach(a => {
                    const href = a.href || '';
                    const text = (a.textContent || '').trim().substring(0, 50);
                    if (href && text) links.push({href, text});
                });
                return links.slice(0, 20);
            }''')

            if nav_links:
                findings['navigation'] = nav_links
                for link in nav_links[:10]:
                    learn(domain, 'navigation_link', link['text'], link['href'], confidence=0.5)

        except Exception:
            pass

        return findings

    def suggest_action(self, domain, goal):
        """Suggest the best action sequence for a goal on a site."""
        from browser_knowledge import recall, get_best_selector, get_pattern

        suggestions = []

        # Check if we have a stored pattern
        pattern = get_pattern(domain, goal)
        if pattern and pattern.get('success_rate', 0) >= 0.5:
            suggestions.append({
                'type': 'pattern',
                'confidence': pattern['success_rate'],
                'steps': pattern['steps'],
                'times_used': pattern.get('times_used', 0),
            })

        # Check known selectors
        if goal in ('login', 'click_login'):
            for field_type in ('username_field', 'password_field', 'login_button'):
                best = get_best_selector(domain, 'click' if field_type == 'login_button' else 'type')
                if best:
                    suggestions.append({
                        'type': 'selector',
                        'field': field_type,
                        'selector': best['selector'],
                        'success_rate': best['success_rate'],
                    })

        return suggestions

    def build_pattern(self, domain, goal, actions):
        """Build and save a pattern from a sequence of successful actions."""
        from browser_knowledge import save_pattern

        if not actions:
            return False

        total_duration = sum(a.get('duration_ms', 0) for a in actions)
        avg_duration = total_duration // len(actions)

        steps = []
        for a in actions:
            step = {
                'action': a.get('action_type', ''),
                'selector': a.get('selector', ''),
                'value': a.get('value', ''),
            }
            steps.append(step)

        return save_pattern(domain, goal, steps, avg_duration, success_rate=1.0)

    def get_site_summary(self, domain):
        """Get a summary of what's been learned about a site."""
        from browser_knowledge import get_site_knowledge, list_patterns, get_action_stats

        knowledge = get_site_knowledge(domain)
        patterns = list_patterns(domain)
        stats = get_action_stats(domain)

        # Categorize knowledge
        selectors = [k for k in knowledge if k['knowledge_type'] == 'selector']
        login_flows = [k for k in knowledge if k['knowledge_type'] == 'login_flow']
        forms = [k for k in knowledge if k['knowledge_type'] == 'form_pattern']
        navigation = [k for k in knowledge if k['knowledge_type'] == 'navigation_link']
        errors = [k for k in knowledge if k['knowledge_type'] in ('unreliable_selector', 'dead_selector', 'site_block')]

        total_actions = sum(s.get('total', 0) for s in stats)
        total_successes = sum(s.get('successes', 0) for s in stats)
        success_rate = round((total_successes / total_actions * 100) if total_actions else 0, 1)

        return {
            'domain': domain,
            'knowledge_count': len(knowledge),
            'selectors': len(selectors),
            'login_flows': len(login_flows),
            'forms': len(forms),
            'navigation_links': len(navigation),
            'known_errors': len(errors),
            'patterns': len(patterns),
            'total_actions': total_actions,
            'success_rate': success_rate,
            'top_selectors': [{'selector': s['key'], 'confidence': s['confidence'],
                               'success_count': s['success_count']}
                              for s in sorted(selectors, key=lambda x: x['confidence'], reverse=True)[:10]],
            'stored_patterns': [{'goal': p['goal'], 'success_rate': p['success_rate'],
                                 'times_used': p['times_used']}
                                for p in patterns[:10]],
        }


# Global singleton
learning_engine = LearningEngine()
