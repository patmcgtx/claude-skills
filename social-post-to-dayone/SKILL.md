---
name: social-post-to-dayone
description: Convert a Reddit or Instagram post into clean markdown the user can paste straight into Day One. Use whenever the user shares a reddit.com, redd.it, or instagram.com link (or pasted page text, or a screenshot) and wants it saved, journaled, archived, formatted, or "made into markdown for DayOne", whatever the post contains (jokes, comics, memes, recipes, tips, quotes, stories, photos). Trigger even when the user only pastes a link and says "save this" or "for DayOne".
---

# Social post to Day One

Turn a Reddit or Instagram post into a markdown entry the user can paste into Day One. The user is keeping these posts as a personal archive, so the entry should read well on its own months later, preserve the original wording, credit where it came from, and be easy to find by tag. The post can be anything: a joke, a recipe, a tip, a quote, a story, a photo with a caption. Do not assume it is a joke.

Pick the path from the link's domain: Reddit (Step 1R) or Instagram (Step 1I). Everything after that is shared.

## Step 1R: Get a Reddit post

Reddit is often off limits to automated tools: web fetching and the in-app browser pane can both refuse reddit.com as a blocked site. Try the quick routes once, and when a site is refused, stop and ask the user for the text rather than hunting for a workaround (mirrors, caches, other tools). A refusal is a boundary, and the user can paste the page text in seconds.

1. Clean the URL: strip tracking and challenge parameters (`utm_*`, `share_id`, `solution`, `js_challenge`, `jsc_*`) and trailing slashes. Keep the subreddit and post id; they go in the source line.
2. Try to open the post in the user's preferred browser (or web fetch if no browser is available). Take the title, body, author, subreddit, and the comments if they are wanted.
3. If the page is refused or unreachable, say so in one line and ask the user to paste the post (title and body, plus a comment if they want one, plus the username if they want credit). The subreddit and post id come from the URL itself, so the source line is still complete; leave out `posted by` if the author is unknown.
4. Pasted page text is full of page chrome: ads, vote counts, "Open chat", sidebar rules, moderator lists. Ignore all of it and pull out only the post and the comments.

## Step 1I: Get an Instagram post

Instagram differs from Reddit: web fetching is blocked by its robots rules, the browser pane needs the user's approval for the site, and the content is usually in the images rather than the caption, which often holds only a teaser.

1. Clean the URL to `https://www.instagram.com/p/<shortcode>/` (or `/reel/<shortcode>/`), dropping `stkn`, `igsh`, `utm_*` and other tracking. Note `img_index` if present: it is one-based (the URL reads `img_index=2` after one click forward), so `img_index=13` means slide 13, and it tells you which slide the user cares about. The page opens on slide 1 regardless, and the current slide is visible in the tab URL as you click through.
2. Open it in the browser pane. If the pane answers that the site is not allowed yet and a `request_access` tool is present, call it with the post URL and scope "once", then retry. If approval is declined or the pane refuses, ask for a screenshot or pasted text instead of finding another route.
3. Read the page text for the account name, caption, and date. Without a login, only a few comments are visible, and they are rarely worth keeping.
4. Take a screenshot to read the images. A sign-up popup usually covers the post; closing it with its X is fine. Never sign up, log in, like, follow, or comment.
5. If the user pointed at a slide (`img_index`, or "slide 13"), click the carousel's right arrow (the circle at the image's right edge) once per slide, ideally several clicks in one batched call, and confirm the tab URL shows the right `img_index`. The keyboard arrow keys do not advance the carousel. The new slide can take a second to load, so wait briefly and re-screenshot if it looks blank. Otherwise read slide 1 and say it is a carousel, offering to read others.
6. If the images cannot be read (login wall, video, text too small), say what was readable and ask for a screenshot or the text.

## Step 2: Work out what the post is

Read the post and let its content set the shape of the entry. Keep the author's wording, spelling, punctuation, and paragraph breaks; do not rewrite, summarize, or "improve" it unless the user asks. Common shapes:

- **Joke with a setup and punchline** (often a Reddit title as setup and body as punchline). Keep the setup as the heading and the punchline below, so the timing survives.
- **Comic, meme, or image post.** Transcribe the text in the image exactly, panel by panel and speaker by speaker, because that text is the content. Add at most one short clause describing the scene when it is needed to make sense of the text (for example, "two women chatting on a Paris street").
- **Recipe, tip, list, or how-to.** Preserve ingredient and step lists as markdown lists in their original order, with quantities exactly as written.
- **Story or long text post.** Keep every paragraph; the user wants the whole thing.
- **Quote or photo with a caption.** Put the quote or caption first, and add a one-line description of the photo if the caption does not make sense without it.

Drop clutter that is not part of the post: "EDIT: thanks for the gold," ads, vote and like counts, "Open chat," sidebar rules, hashtag walls at the end of Instagram captions (keep one or two if they carry meaning), and repost disclaimers. If the post is `[removed]` or `[deleted]` with nothing to save, tell the user instead of producing an empty entry.

## Step 3: Decide about comments

Include a single comment only if it adds to the post: a good follow-up or callback on a joke, a correction or useful addition on a tip or recipe, a clarification of a story. Skip bots, moderator notices, "this is a repost," award thank-yous, arguments, and plain restatements. For Reddit, check the best-sorted comments first. Instagram comments are rarely worth keeping. If nothing qualifies, leave the section out entirely rather than padding it. If the user asked for more comments, or for none, follow that.

## Step 4: Write the markdown

Day One renders standard markdown, so use simple structure: a heading, paragraphs, lists, blockquotes, and a tag line. Avoid tables, HTML, and embedded images (remote image links do not import into Day One).

```markdown
# {Title}

{Body, in the shape that fits the content}

---

**Top reply** (u/{comment_author}):
> {comment body}

*Source: [{r/subreddit or @account}]({clean_post_url}) · posted by {u/author}*

#{type tag} #{platform tag} #{community or account tag}
```

Rules for filling it in:

- **Title.** Use the post title for Reddit. For Instagram, use the first line of the caption, or the setup line of a joke, or a short descriptive title if neither works. Keep it under about 80 characters.
- **Spacing.** Put a blank line between every block so Day One does not merge paragraphs. Use `>` on every line of a multi-line quote.
- **Dialogue.** For comics with clear speakers, write `> **Name or "Left":** text`, one line per speaker. For a single-image meme, use one blockquote with no labels.
- **Source line.** Use the clean post URL, never the share link. Add `· slide N` for a specific Instagram slide. Leave out `posted by` when the author is unknown. For Instagram the account is already in the source link, so do not repeat it.
- **Tags.** One line at the end, lowercase, no spaces inside a tag. Always include the platform (`#reddit` or `#instagram`) and the community or account (`#dadjokes`, `#wannakissyourscars`). Add one type tag that describes the content when it is obvious (`#joke`, `#recipe`, `#tip`, `#quote`, `#comic`, `#story`). Do not invent several topical tags.
- **No comment.** If no comment is used, leave out the "Top reply" block and the `---` above it.
- **Standing tag rules.** Some accounts and communities always get an extra tag, added on top of the usual ones. Apply every rule that matches:
  - Posts from Instagram account `@wannakissyourscars` get `#momjoke`.
  To add a rule, the user just says something like "tag all posts from X as #Y"; add it to this list when updating the skill.

## Step 5: Deliver it

Reply with the markdown in a single code block so the user can copy it in one click. Add at most one short line after it if something was skipped, trimmed, or unreadable (for example, "Left out the top reply since it was a bot," or "This is a carousel; I read slide 1"). Do not explain the template or recap the steps. Only create a file if the user asks for one.

## Examples

**Reddit joke.** Input: a link to an r/dadjokes post titled "Why do pancakes always win at baseball?" with the body "Because they have the best batter." and a top reply riffing on the lineup.

```markdown
# Why do pancakes always win at baseball?

Because they have the best batter.

---

**Top reply** (u/what_da_funk_is_this):
> And their lineup is stacked!!!

*Source: [r/dadjokes](https://www.reddit.com/r/dadjokes/comments/1wxiogg/why_do_pancakes_always_win_at_baseball/) · posted by u/monorico*

#joke #reddit #dadjokes
```

**Instagram comic.** Input: a link to an Instagram post by @wannakissyourscars, caption "Some of us just want a man who irons his own shirts", with a comic of two women talking.

```markdown
# Some of us just want a man who irons his own shirts

*Two women chatting on a Paris street.*

> **Left:** Watch out! He only wants to take you to bed!
> **Right:** Thank goodness! I was afraid I'd have to iron his shirts!

*Source: [@wannakissyourscars](https://www.instagram.com/p/Dd7V0fek7It/) · slide 1*

#comic #instagram #wannakissyourscars
```