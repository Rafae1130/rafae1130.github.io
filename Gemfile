source "https://rubygems.org"

# Built by GitHub Actions rather than the legacy Pages builder, so the
# Jekyll version is chosen here instead of being pinned to 3.10 by the
# github-pages gem. Jekyll 4 is what makes `mark_lines` available.
gem "jekyll", "~> 4.3"
gem "jekyll-theme-cayman"

# The github-pages gem used to enable most of these implicitly. Naming
# them here is what keeps the site building the same way: the posts and
# README carry no front matter, and the README is the homepage.
group :jekyll_plugins do
  gem "jekyll-seo-tag"
  gem "jekyll-sitemap"
  gem "jekyll-feed"
  gem "jekyll-optional-front-matter"
  gem "jekyll-readme-index"
  gem "jekyll-relative-links"
  gem "jekyll-titles-from-headings"
  gem "jekyll-default-layout"
  # Cayman appends site.github.build_revision to the stylesheet URL as a
  # cache-buster. Without this the query string is empty and readers keep
  # the old CSS after a change.
  gem "jekyll-github-metadata"
end

# Ruby 3 dropped webrick from stdlib, and `jekyll serve` needs it.
gem "webrick", "~> 1.8"
