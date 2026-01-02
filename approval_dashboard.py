import json
import os
from datetime import datetime
import gradio as gr
import re

DATA_PATH = "data/input_data.json"
APPROVED_PATH = "data/approved_replies.json"
REJECTED_PATH = "data/rejected_replies.json"

# Auto-approve thresholds
AUTO_APPROVE_THRESHOLDS = {
    "intent_score": 0.7,
    "reply_score": 0.85
}

# ----------------------------
# Reply Scoring System
# ----------------------------

def extract_keywords(text):
    """Extract important keywords from text"""
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
                   'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 
                   'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 
                   'might', 'can', 'what', 'how', 'why', 'when', 'where', 'who'}
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    keywords = [w for w in words if w not in stop_words]
    return keywords

def calculate_relevance_score(post_text, reply_text):
    """Calculate how relevant the reply is to the post (0-1)"""
    post_keywords = set(extract_keywords(post_text))
    reply_keywords = set(extract_keywords(reply_text))
    
    if not post_keywords:
        return 0.5
    
    overlap = len(post_keywords.intersection(reply_keywords))
    relevance = min(overlap / len(post_keywords), 1.0)
    
    if len(reply_text) > 100:
        relevance = min(relevance + 0.1, 1.0)
    
    return relevance

def calculate_tone_score(reply_text, tone):
    """Calculate tone appropriateness score (0-1)"""
    tone_scores = {
        'educational': 0.95,
        'consultative': 0.90,
        'promotional': 0.70
    }
    
    base_score = tone_scores.get(tone, 0.75)
    
    spam_indicators = ['click here', 'buy now', '!!!', 'limited time', 'act now', 'dm me']
    spam_count = sum(1 for indicator in spam_indicators if indicator in reply_text.lower())
    
    if spam_count > 0:
        base_score *= (0.8 ** spam_count)
    
    return base_score

def calculate_engagement_score(reply_text):
    """Calculate potential engagement quality (0-1)"""
    score = 0.5
    
    if '?' in reply_text:
        score += 0.15
    if len(reply_text) > 80:
        score += 0.15
    if len(reply_text.split('.')) >= 2:
        score += 0.10
    if any(char.isdigit() for char in reply_text):
        score += 0.10
    
    if reply_text.isupper():
        score -= 0.3
    if reply_text.count('!') > 2:
        score -= 0.2
    
    return max(0, min(score, 1.0))

def calculate_brand_safety_score(reply_text):
    """Calculate brand safety score (0-1)"""
    score = 1.0
    
    red_flags = {
        'click here': 0.3,
        'buy now': 0.3,
        'limited time': 0.2,
        '!!!': 0.2,
        'dm me': 0.15,
        'link in bio': 0.15,
    }
    
    for flag, penalty in red_flags.items():
        if flag in reply_text.lower():
            score -= penalty
    
    if sum(1 for c in reply_text if c.isupper()) > len(reply_text) * 0.3:
        score -= 0.2
    
    if reply_text and not reply_text[0].isupper():
        score -= 0.1
    
    return max(0, score)

def calculate_compliance_score(reply_text):
    """Calculate compliance/ethics score (0-1)"""
    score = 1.0
    
    suspicious_phrases = ['i found this', 'stumbled upon', 'happened to find', 'randomly discovered']
    for phrase in suspicious_phrases:
        if phrase in reply_text.lower():
            score -= 0.3
            break
    
    aggressive_phrases = ['must try', 'you need', 'you have to', 'best ever', 'only option']
    for phrase in aggressive_phrases:
        if phrase in reply_text.lower():
            score -= 0.15
    
    return max(0, score)

def calculate_reply_score(post, reply):
    """Calculate comprehensive reply score (0-1)"""
    relevance = calculate_relevance_score(post['post_text'], reply['text'])
    tone = calculate_tone_score(reply['text'], reply.get('tone', 'promotional'))
    engagement = calculate_engagement_score(reply['text'])
    brand_safety = calculate_brand_safety_score(reply['text'])
    compliance = calculate_compliance_score(reply['text'])
    
    final_score = (
        relevance * 0.30 +
        tone * 0.20 +
        engagement * 0.20 +
        brand_safety * 0.15 +
        compliance * 0.15
    )
    
    return round(final_score, 2)

def recalculate_all_scores():
    """Recalculate scores for all posts and save"""
    posts = load_posts()
    
    for post in posts:
        for reply in post['reply_options']:
            new_score = calculate_reply_score(post, reply)
            reply['reply_score'] = new_score
            reply['score_breakdown'] = {
                'relevance': round(calculate_relevance_score(post['post_text'], reply['text']), 2),
                'tone': round(calculate_tone_score(reply['text'], reply.get('tone', 'promotional')), 2),
                'engagement': round(calculate_engagement_score(reply['text']), 2),
                'brand_safety': round(calculate_brand_safety_score(reply['text']), 2),
                'compliance': round(calculate_compliance_score(reply['text']), 2)
            }
    
    with open(DATA_PATH, 'w') as f:
        json.dump(posts, f, indent=2)
    
    return posts

# ----------------------------
# Data Utilities
# ----------------------------

def load_posts():
    """Load posts from JSON file"""
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r") as f:
                content = f.read().strip()
                if not content:
                    return []
                return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            print(f"Error loading {DATA_PATH}.")
            return []
    return []

def save_approved(post, reply):
    """Save approved reply to JSON"""
    approved_item = {
        "post_id": post["post_id"],
        "platform": post["platform"],
        "author": post["author"],
        "timestamp": post["timestamp"],
        "post_text": post["post_text"],
        "intent_score": post["intent_score"],
        "approved_reply": reply,
        "approved_at": datetime.utcnow().isoformat()
    }
    
    approved = []
    if os.path.exists(APPROVED_PATH):
        try:
            with open(APPROVED_PATH, "r") as f:
                content = f.read().strip()
                if content:
                    approved = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            approved = []
    
    approved.append(approved_item)
    os.makedirs(os.path.dirname(APPROVED_PATH), exist_ok=True)
    with open(APPROVED_PATH, "w") as f:
        json.dump(approved, f, indent=2)

def save_rejected(post, reply):
    """Save rejected reply to JSON"""
    rejected_item = {
        "post_id": post["post_id"],
        "platform": post["platform"],
        "author": post["author"],
        "timestamp": post["timestamp"],
        "post_text": post["post_text"],
        "intent_score": post["intent_score"],
        "rejected_reply": reply,
        "rejected_at": datetime.utcnow().isoformat()
    }
    
    rejected = []
    if os.path.exists(REJECTED_PATH):
        try:
            with open(REJECTED_PATH, "r") as f:
                content = f.read().strip()
                if content:
                    rejected = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            rejected = []
    
    rejected.append(rejected_item)
    os.makedirs(os.path.dirname(REJECTED_PATH), exist_ok=True)
    with open(REJECTED_PATH, "w") as f:
        json.dump(rejected, f, indent=2)

def load_approved():
    """Load approved replies"""
    if os.path.exists(APPROVED_PATH):
        try:
            with open(APPROVED_PATH, "r") as f:
                content = f.read().strip()
                if not content:
                    return []
                return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return []
    return []

def load_rejected():
    """Load rejected replies"""
    if os.path.exists(REJECTED_PATH):
        try:
            with open(REJECTED_PATH, "r") as f:
                content = f.read().strip()
                if not content:
                    return []
                return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return []
    return []

# ----------------------------
# App State
# ----------------------------

posts = load_posts()
post_lookup = {p["post_id"]: p for p in posts}

def get_score_badge(score, label="Score"):
    """Return HTML badge with color coding"""
    percentage = int(score * 100)
    
    if score >= 0.85:
        color = "#10b981"
        bg = "#d1fae5"
    elif score >= 0.7:
        color = "#f59e0b"
        bg = "#fef3c7"
    else:
        color = "#ef4444"
        bg = "#fee2e2"
    
    return f'<span style="background: {bg}; color: {color}; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600;">{label}: {percentage}%</span>'

def should_auto_approve(post, reply):
    """Check if reply meets auto-approve criteria"""
    return (post["intent_score"] >= AUTO_APPROVE_THRESHOLDS["intent_score"] and 
            reply["reply_score"] >= AUTO_APPROVE_THRESHOLDS["reply_score"])

def get_post_options():
    """Get formatted post options for dropdown"""
    return [f'{p["post_id"]} | {p["platform"]} | Intent: {int(p["intent_score"]*100)}%' for p in posts]

def check_reply_status(post_id, reply_text):
    """Check if a reply has been approved or rejected"""
    # Check approved
    approved = load_approved()
    for item in approved:
        if item['post_id'] == post_id and item['approved_reply']['text'] == reply_text:
            return 'approved'
    
    # Check rejected
    rejected = load_rejected()
    for item in rejected:
        if item['post_id'] == post_id and item['rejected_reply']['text'] == reply_text:
            return 'rejected'
    
    return None

def display_post_details(selection):
    """Display selected post details"""
    if not selection:
        return "", gr.update(visible=False), None
    
    post_id = selection.split(" | ")[0]
    post = post_lookup[post_id]
    
    # Post metadata
    metadata_html = f"""<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; margin-bottom: 20px; color: white;'>
        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;'>
            <span style='font-size: 14px; font-weight: 600;'>{post['platform']}</span>
            {get_score_badge(post['intent_score'], 'Intent Score')}
        </div>
        <div style='font-size: 13px; opacity: 0.9;'>
            <strong>Author:</strong> @{post['author']} | <strong>Posted:</strong> {post['timestamp']}
        </div>
    </div>
    """
    
    # Post text
    post_text_html = f"""<div style='background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; border-left: 4px solid #667eea;'>
        <div style='font-weight: 600; margin-bottom: 10px; color: #667eea;'>Original Post</div>
        <div style='color: #374151; line-height: 1.6;'>{post['post_text']}</div>
    </div>
    """
    
    combined_html = metadata_html + post_text_html
    
    return combined_html, gr.update(visible=True), post_id

def display_replies(post_id):
    """Display all replies for a post"""
    if not post_id:
        return []
    
    post = post_lookup[post_id]
    replies_html = []
    
    for i, reply in enumerate(post['reply_options']):
        auto_approve = should_auto_approve(post, reply)
        auto_badge = '<span style="background: #10b981; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; margin-left: 8px;">✓ Auto-Approve Eligible</span>' if auto_approve else ''
        
        breakdown = reply.get('score_breakdown', {})
        breakdown_html = f"""<div style='font-size: 11px; color: #6b7280; margin-top: 8px;'>
            <strong>Score Breakdown:</strong> 
            Relevance: {int(breakdown.get('relevance', 0)*100)}% | 
            Tone: {int(breakdown.get('tone', 0)*100)}% | 
            Engagement: {int(breakdown.get('engagement', 0)*100)}% | 
            Safety: {int(breakdown.get('brand_safety', 0)*100)}% | 
            Compliance: {int(breakdown.get('compliance', 0)*100)}%
        </div>
        """ if breakdown else ""
        
        # Check status
        status = check_reply_status(post_id, reply['text'])
        
        if status == 'approved':
            bg_color = '#d1fae5'
            border_color = '#10b981'
            status_badge = '<span style="background: #10b981; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600;">✅ APPROVED</span>'
        elif status == 'rejected':
            bg_color = '#fee2e2'
            border_color = '#ef4444'
            status_badge = '<span style="background: #ef4444; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600;">🚫 REJECTED</span>'
        else:
            bg_color = '#f9fafb'
            border_color = '#e5e7eb'
            status_badge = ''
        
        reply_html = f"""<div style='background: {bg_color}; padding: 20px; border-radius: 10px; margin-bottom: 15px; border-left: 4px solid {border_color};'>
            <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;'>
                <div style='display: flex; align-items: center; gap: 8px; flex-wrap: wrap;'>
                    <span style='font-weight: 600; color: #111827;'>Reply {i+1}</span>
                    {get_score_badge(reply['reply_score'], 'Reply Score')}
                    <span style='background: #e0e7ff; color: #4338ca; padding: 4px 8px; border-radius: 4px; font-size: 11px;'>{reply['tone']}</span>
                    {auto_badge}
                    {status_badge}
                </div>
            </div>
            {breakdown_html}
            <div style='color: #374151; line-height: 1.6; margin-top: 12px;'>{reply['text']}</div>
        </div>
        """
        
        replies_html.append((reply_html, i))
    
    return replies_html

def approve_reply_action(post_id, reply_index):
    """Approve the selected reply"""
    if not post_id or reply_index is None:
        return "❌ Error approving reply.", []
    
    post = post_lookup[post_id]
    reply = post['reply_options'][reply_index]
    save_approved(post, reply)
    
    # Return updated replies
    return f"✅ Approved reply {reply_index + 1} for post {post_id} successfully!", display_replies(post_id)

def reject_reply_action(post_id, reply_index):
    """Reject the selected reply"""
    if not post_id or reply_index is None:
        return "❌ Error rejecting reply.", []
    
    post = post_lookup[post_id]
    reply = post['reply_options'][reply_index]
    save_rejected(post, reply)
    
    # Return updated replies
    return f"🚫 Rejected reply {reply_index + 1} for post {post_id}.", display_replies(post_id)

def delete_approved_item(index):
    """Delete an approved item by index"""
    approved = load_approved()
    if 0 <= index < len(approved):
        deleted_item = approved.pop(index)
        with open(APPROVED_PATH, 'w') as f:
            json.dump(approved, f, indent=2)
        return f"✅ Deleted approved reply for post {deleted_item['post_id']}"
    return "❌ Error deleting approved reply"

def get_approved_history():
    """Display approved history"""
    approved = load_approved()
    if not approved:
        return '<div style="padding: 20px; text-align: center; color: #6b7280;">No approved replies yet</div>', []
    
    html = f'<div style="font-weight: 600; margin-bottom: 20px; font-size: 16px; color: #10b981;">✅ Approved Posts ({len(approved)})</div>'
    
    items_data = []
    for i, item in enumerate(approved):
        html += f"""<div style='background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); padding: 20px; border-radius: 10px; margin-bottom: 15px; border-left: 4px solid #10b981; box-shadow: 0 2px 4px rgba(0,0,0,0.1); position: relative;'>
            <div style='display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;'>
                <div>
                    <div style='background: #10b981; color: white; padding: 4px 12px; border-radius: 4px; font-size: 11px; font-weight: 600; display: inline-block; margin-bottom: 8px;'>✅ APPROVED</div>
                    <div style='font-size: 11px; color: #059669; font-weight: 500;'>{item['approved_at']}</div>
                </div>
                <div style='display: flex; gap: 8px; align-items: center;'>
                    <div style='background: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; color: #6b7280;'>
                        <strong>Platform:</strong> {item['platform']} | <strong>Author:</strong> @{item['author']}
                    </div>
                    <div id='delete-approved-{i}' style='background: #ef4444; color: white; padding: 6px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer; hover: opacity: 0.9;'>🗑️ Delete</div>
                </div>
            </div>
            <div style='background: white; padding: 15px; border-radius: 6px; margin-bottom: 12px;'>
                <div style='font-weight: 600; margin-bottom: 8px; color: #374151; font-size: 13px;'>📝 Original Post</div>
                <div style='color: #374151; line-height: 1.6;'>{item['post_text']}</div>
            </div>
            <div style='background: rgba(16, 185, 129, 0.1); padding: 15px; border-radius: 6px; border-left: 3px solid #10b981;'>
                <div style='font-weight: 600; margin-bottom: 8px; color: #059669; font-size: 13px;'>💬 Approved Reply</div>
                <div style='color: #374151; line-height: 1.6;'>{item['approved_reply']['text']}</div>
            </div>
        </div>
        """
        items_data.append(i)
    
    return html, items_data

def delete_rejected_item(index):
    """Delete a rejected item by index"""
    rejected = load_rejected()
    if 0 <= index < len(rejected):
        deleted_item = rejected.pop(index)
        with open(REJECTED_PATH, 'w') as f:
            json.dump(rejected, f, indent=2)
        return f"✅ Deleted rejected reply for post {deleted_item['post_id']}"
    return "❌ Error deleting rejected reply"

def get_rejected_history():
    """Display rejected history"""
    rejected = load_rejected()
    if not rejected:
        return '<div style="padding: 20px; text-align: center; color: #6b7280;">No rejected replies yet</div>', []
    
    html = f'<div style="font-weight: 600; margin-bottom: 20px; font-size: 16px; color: #ef4444;">🚫 Rejected Replies ({len(rejected)})</div>'
    
    items_data = []
    for i, item in enumerate(rejected):
        html += f"""<div style='background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%); padding: 20px; border-radius: 10px; margin-bottom: 15px; border-left: 4px solid #ef4444; box-shadow: 0 2px 4px rgba(0,0,0,0.1); position: relative;'>
            <div style='display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;'>
                <div>
                    <div style='background: #ef4444; color: white; padding: 4px 12px; border-radius: 4px; font-size: 11px; font-weight: 600; display: inline-block; margin-bottom: 8px;'>🚫 REJECTED</div>
                    <div style='font-size: 11px; color: #dc2626; font-weight: 500;'>{item['rejected_at']}</div>
                </div>
                <div style='display: flex; gap: 8px; align-items: center;'>
                    <div style='background: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; color: #6b7280;'>
                        <strong>Platform:</strong> {item['platform']} | <strong>Author:</strong> @{item['author']}
                    </div>
                    <div id='delete-rejected-{i}' style='background: #ef4444; color: white; padding: 6px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer; hover: opacity: 0.9;'>🗑️ Delete</div>
                </div>
            </div>
            <div style='background: white; padding: 15px; border-radius: 6px; margin-bottom: 12px;'>
                <div style='font-weight: 600; margin-bottom: 8px; color: #374151; font-size: 13px;'>📝 Original Post</div>
                <div style='color: #374151; line-height: 1.6;'>{item['post_text']}</div>
            </div>
            <div style='background: rgba(239, 68, 68, 0.1); padding: 15px; border-radius: 6px; border-left: 3px solid #ef4444;'>
                <div style='font-weight: 600; margin-bottom: 8px; color: #dc2626; font-size: 13px;'>💬 Rejected Reply</div>
                <div style='color: #374151; line-height: 1.6;'>{item['rejected_reply']['text']}</div>
            </div>
        </div>
        """
        items_data.append(i)
    
    return html, items_data

# ----------------------------
# UI
# ----------------------------

with gr.Blocks(title="LeadEquator Approval Dashboard", css="""
    .reply-container { margin-top: 20px; }
""") as demo:
    gr.Markdown("""
    # 🎯 LeadEquator Approval Dashboard
    Review high-intent conversations and approve replies before posting
    """)
    
    # Button to recalculate scores
    with gr.Row():
        recalc_btn = gr.Button("🔄 Recalculate All Reply Scores", variant="secondary", size="sm")
        recalc_status = gr.Markdown("")
    
    with gr.Tabs():
        # ===== APPROVAL QUEUE TAB =====
        with gr.TabItem(f"📋 Approval Queue ({len(posts)})", id="queue_tab"):
            with gr.Row():
                post_selector = gr.Dropdown(
                    label="Select Post to Review",
                    choices=get_post_options(),
                    interactive=True
                )
            
            post_details = gr.HTML()
            current_post_id = gr.State()
            
            action_group = gr.Group(visible=False)
            with action_group:
                status_msg = gr.Markdown()
                
                # Create reply display components (max 10 replies per post)
                reply_components = []
                for i in range(10):
                    with gr.Group(visible=False, elem_classes="reply-container") as reply_group:
                        reply_html = gr.HTML()
                        with gr.Row():
                            approve_btn = gr.Button("👍 Approve", variant="primary", size="sm")
                            reject_btn = gr.Button("👎 Reject", variant="stop", size="sm")
                    reply_components.append({
                        'group': reply_group,
                        'html': reply_html,
                        'approve': approve_btn,
                        'reject': reject_btn,
                        'index': i
                    })
            
            # Post selection handler
            def handle_post_selection(selection):
                if not selection:
                    outputs = ["", gr.update(visible=False), None]
                    for _ in reply_components:
                        outputs.extend([gr.update(visible=False), ""])
                    return outputs
                
                post_html, action_visible, post_id = display_post_details(selection)
                replies_data = display_replies(post_id)
                
                outputs = [post_html, action_visible, post_id]
                
                for i, comp in enumerate(reply_components):
                    if i < len(replies_data):
                        reply_html_content, _ = replies_data[i]
                        outputs.extend([gr.update(visible=True), reply_html_content])
                    else:
                        outputs.extend([gr.update(visible=False), ""])
                
                return outputs
            
            post_outputs = [post_details, action_group, current_post_id]
            for comp in reply_components:
                post_outputs.extend([comp['group'], comp['html']])
            
            post_selector.change(
                fn=handle_post_selection,
                inputs=[post_selector],
                outputs=post_outputs
            )
            
            # Connect approve/reject buttons for each reply
            for comp in reply_components:
                idx = comp['index']
                
                # Approve handler
                def make_approve_handler(reply_idx):
                    def handler(post_id):
                        status, replies_data = approve_reply_action(post_id, reply_idx)
                        outputs = [status]
                        for i, c in enumerate(reply_components):
                            if i < len(replies_data):
                                reply_html_content, _ = replies_data[i]
                                outputs.extend([gr.update(visible=True), reply_html_content])
                            else:
                                outputs.extend([gr.update(visible=False), ""])
                        return outputs
                    return handler
                
                # Reject handler
                def make_reject_handler(reply_idx):
                    def handler(post_id):
                        status, replies_data = reject_reply_action(post_id, reply_idx)
                        outputs = [status]
                        for i, c in enumerate(reply_components):
                            if i < len(replies_data):
                                reply_html_content, _ = replies_data[i]
                                outputs.extend([gr.update(visible=True), reply_html_content])
                            else:
                                outputs.extend([gr.update(visible=False), ""])
                        return outputs
                    return handler
                
                button_outputs = [status_msg]
                for c in reply_components:
                    button_outputs.extend([c['group'], c['html']])
                
                comp['approve'].click(
                    fn=make_approve_handler(idx),
                    inputs=[current_post_id],
                    outputs=button_outputs
                )
                
                comp['reject'].click(
                    fn=make_reject_handler(idx),
                    inputs=[current_post_id],
                    outputs=button_outputs
                )
        
        # ===== APPROVED HISTORY TAB =====
        with gr.TabItem("✅ Approved", id="approved_tab"):
            approved_display = gr.HTML(value=get_approved_history()[0])
            approved_items_state = gr.State([])
            
            with gr.Row():
                refresh_approved = gr.Button("🔄 Refresh", size="sm", variant="secondary")
            
            approved_status = gr.Markdown()
            
            # Create delete buttons for approved items (max 20 items shown)
            approved_delete_buttons = []
            for i in range(20):
                delete_btn = gr.Button(f"🗑️ Delete Item {i}", visible=False, variant="stop", size="sm")
                approved_delete_buttons.append(delete_btn)
            
            def refresh_approved_display():
                html, items = get_approved_history()
                updates = [html, items, ""]
                for i, btn in enumerate(approved_delete_buttons):
                    updates.append(gr.update(visible=(i < len(items))))
                return updates
            
            outputs = [approved_display, approved_items_state, approved_status]
            for btn in approved_delete_buttons:
                outputs.append(btn)
            
            refresh_approved.click(
                fn=refresh_approved_display,
                outputs=outputs
            )
            
            # Connect delete buttons
            for i, delete_btn in enumerate(approved_delete_buttons):
                def make_delete_handler(idx):
                    def handler():
                        status = delete_approved_item(idx)
                        html, items = get_approved_history()
                        updates = [status, html, items]
                        for j, btn in enumerate(approved_delete_buttons):
                            updates.append(gr.update(visible=(j < len(items))))
                        return updates
                    return handler
                
                delete_btn.click(
                    fn=make_delete_handler(i),
                    outputs=[approved_status, approved_display, approved_items_state] + approved_delete_buttons
                )
        
        # ===== REJECTED HISTORY TAB =====
        with gr.TabItem("🚫 Rejected", id="rejected_tab"):
            rejected_display = gr.HTML(value=get_rejected_history()[0])
            rejected_items_state = gr.State([])
            
            with gr.Row():
                refresh_rejected = gr.Button("🔄 Refresh", size="sm", variant="secondary")
            
            rejected_status = gr.Markdown()
            
            # Create delete buttons for rejected items (max 20 items shown)
            rejected_delete_buttons = []
            for i in range(20):
                delete_btn = gr.Button(f"🗑️ Delete Item {i}", visible=False, variant="stop", size="sm")
                rejected_delete_buttons.append(delete_btn)
            
            def refresh_rejected_display():
                html, items = get_rejected_history()
                updates = [html, items, ""]
                for i, btn in enumerate(rejected_delete_buttons):
                    updates.append(gr.update(visible=(i < len(items))))
                return updates
            
            outputs = [rejected_display, rejected_items_state, rejected_status]
            for btn in rejected_delete_buttons:
                outputs.append(btn)
            
            refresh_rejected.click(
                fn=refresh_rejected_display,
                outputs=outputs
            )
            
            # Connect delete buttons
            for i, delete_btn in enumerate(rejected_delete_buttons):
                def make_delete_handler(idx):
                    def handler():
                        status = delete_rejected_item(idx)
                        html, items = get_rejected_history()
                        updates = [status, html, items]
                        for j, btn in enumerate(rejected_delete_buttons):
                            updates.append(gr.update(visible=(j < len(items))))
                        return updates
                    return handler
                
                delete_btn.click(
                    fn=make_delete_handler(i),
                    outputs=[rejected_status, rejected_display, rejected_items_state] + rejected_delete_buttons
                )
    
    # Recalculate scores button
    def on_recalculate():
        recalculate_all_scores()
        global posts, post_lookup
        posts = load_posts()
        post_lookup = {p["post_id"]: p for p in posts}
        return "✅ All reply scores recalculated!", gr.update(choices=get_post_options())
    
    recalc_btn.click(
        fn=on_recalculate,
        outputs=[recalc_status, post_selector]
    )

if __name__ == "__main__":
    # Recalculate scores on startup if needed
    print("Checking reply scores...")
    if posts and any('reply_score' not in reply for post in posts for reply in post.get('reply_options', [])):
        print("Calculating missing reply scores...")
        recalculate_all_scores()
        posts = load_posts()
        post_lookup = {p["post_id"]: p for p in posts}
        print("Reply scores calculated!")
    
    demo.launch(
        share=False,
        theme=gr.themes.Soft(primary_hue="blue", secondary_hue="gray"),
    )