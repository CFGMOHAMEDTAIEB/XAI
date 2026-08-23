# XAI-Compress Public Website

Next.js, React and TypeScript public-facing website for product presentation, documentation entry points, downloads, pricing, service status and legal placeholders.

## Included pages

- Landing page
- Features
- Security
- Architecture
- Downloads
- Pricing
- Documentation
- Status
- Contact
- Privacy and terms placeholders
- SEO metadata, robots and sitemap

## Integrate into the monorepo

Replace:

```text
XAI-COMPRESS-PLATFORM/apps/public_nextjs
```

with this folder. Avoid nesting `public_nextjs/public_nextjs`.

## Requirements

Install Node.js. Verify:

```bat
node --version
npm --version
```

## Install and run

```bat
cd apps\public_nextjs
copy .env.example .env.local
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The **Open cloud portal** button points to `http://localhost:4200` by default.

## Production build

```bat
npm run typecheck
npm run build
npm start
```

## Docker

```bat
docker build -t xai-public-nextjs .
docker run --rm -p 3000:3000 --env-file .env.local xai-public-nextjs
```

## Important scope

The website deliberately labels benchmark figures in the hero representation as illustrative. Replace figures only with generated held-out benchmark evidence. Download buttons remain disabled until signed release binaries exist. Privacy and terms pages require legal review.
