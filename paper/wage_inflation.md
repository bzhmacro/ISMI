---
title: "The Spiral Gain"
subtitle: "Wage indexation, statutory floors and fiscal handouts: how much of an inflation shock returns as income, and how much of that income returns as inflation"
tagline: "How much of an inflation shock returns as income, and how much of that income returns as inflation"
author: bzhmacro — bretagnemacro@gmail.com
date: 2026-09-14
abstract: >
  We ask whether consumer price inflation feeds back into household incomes, and
  whether governments close that loop when labour markets do not. We build a
  hand-collected database of wage indexation for seven advanced economies from
  1960 — contractual escalators, statutory indexation of public pay,
  price-indexed wage floors, a formal role for inflation in bargaining — and map
  it into one state variable, the indexation intensity lambda. Interacting it
  with a one-sided real-wage gap in a partially pooled Bernanke-Blanchard wage
  equation — country-specific dynamics, a common catch-up block — we estimate
  Lambda, the three-year recovery of a real-wage loss. A Chow test decisively
  rejects full pooling, and freeing the dynamics cuts the catch-up interaction
  by two-thirds, from +0.339 to +0.110: most of the apparent indexation effect
  under full pooling is misspecification, which we report rather than bury. What
  survives is the sign. dLambda/dlambda is positive in all seven countries,
  +0.102 to +0.364, so more indexation means more real-wage recovery everywhere;
  the level of Lambda is persistence-dominated and not comparable across
  countries. Combining Lambda with country-specific wage-to-price pass-through M
  gives the Spiral Gain G = Lambda x M, negative in all seven countries today:
  no economy in the panel has a self-reinforcing loop. Belgium pairs the highest
  lambda with an M of -0.083, which is why its indexation has never produced
  excess inflation. An Effective Wage Index adding statutory floors, indexed
  benefits and handouts to market pay shows the bottom quartile tracking the
  average within a point.
keywords:
  - wage indexation
  - wage-price spiral
  - cost-of-living adjustment
  - minimum wage
  - benefit uprating
  - energy subsidies
  - fiscal transfers
  - Phillips curve
  - pass-through
  - effective wage index
---

# The Spiral Gain

A wage–price spiral is a product, not a sum. It requires that prices come back as wages, and that wages go back out as prices. This paper measures both halves separately, for seven advanced economies over sixty-five years, using an institutional database of who is indexed to what; and it asks what happens to the loop when the government, rather than the labour market, is the agent that returns the inflation to households.

## Introduction

The question is narrow and old: when the consumer price level jumps, does that jump come back as household income, and if it does, does the income come back as prices? The 1970s answer was yes on both counts. The 2021–24 answer was, on the evidence assembled here and elsewhere, no on the first almost everywhere and only partially on the second. What changed was not the shock, and on any evidence we can find not the way firms set prices. What changed was the set of institutions that convert a realised price level into a contractual wage claim.

That set of institutions is the object of this paper, and we treat it as observable rather than latent. Bernanke and Blanchard (2025) write a wage equation in which past inflation surprises enter with a constant coefficient, and find it economically and statistically indistinguishable from zero in the United States before the pandemic (sum of lags −0.024, *p* = 0.77); their multi-country extension finds the same near-zero in most of eleven economies (Bernanke and Blanchard 2024). Theory says the coefficient should not be a constant: Afrouzi, Blanco, Drenik and Hurst (2024) microfound a catch-up parameter that is state-dependent rather than structural. The euro-area evidence is consistent with that though weaker than the theory — the ECB's post-mortem reports that catch-up was a dominant driver of wage growth after the shock while the prevalence of formal indexation remained low, a statement about the size of the *contribution*, not about a rising *coefficient* (Bates, Bodnár, Healy and Roca I Llevadot 2025). The standard response would be to filter a latent time-varying parameter. We do something more literal: we build the state variable from institutions — statutes, collective-agreement coverage statistics, minimum-wage legislation, central-bank surveys — and interact it with the catch-up term directly.

The paper proceeds along three angles, corresponding to three ways an inflation shock can be returned to a household. The first is **formal indexation**: a contractual escalator, a statutory rule for public pay, or a named role for inflation in a bargaining round — the classical channel, the one Gray (1976) and Fischer (1977b) modelled. We assemble coverage shares for four such channels by country and year and collapse them into a single intensity $\lambda_t \in [0,1]$. The second is **statutory wage floors and benefit uprating**. A price-indexed minimum wage, or a pension uprated by a legislated formula, transmits the price level into incomes as surely as a COLA clause, but outside the bargaining system and invisible in every negotiated-wage indicator. France is the sharp case: the 1983 *désindexation* prohibited general wage indexation but left the SMIC formula in force, so the French wage floor has been continuously price-indexed since 1952 while French wage bargaining has not been since 1983. The United Kingdom is the other, where the triple lock delivered pension upratings of 10.1% and 8.5% while negotiated pay did nothing of the kind. The third is **discretionary handouts and subsidies**: between September 2021 and January 2023 European governments allocated €758.3 billion, roughly 4.4% of GDP on average, to shielding households and firms from energy prices (Sgaravatti, Tagliapietra, Trasi and Zachmann 2023), roughly half acting on prices and half on incomes (Bańkowski et al. 2023). The statistical treatment of the two is entirely different — a per-unit cap enters the HICP and a lump-sum payment does not (Eurostat 2022) — while their effect on purchasing power is similar. Any wage or price equation estimated across 2021–24 that ignores the distinction is mis-specified, and any measure of real income using the published CPI is using a deflator that policy has moved.

**Contribution.** Three. First, an institutional database: 94 sourced coverage observations across seven countries, 1960–2026, four channels, each row carrying its source and, where it is a derived number, its derivation. Second, a decomposition of the spiral into a product of two separately estimated gains — the price-to-wage catch-up $\Lambda(\lambda)$ and the wage-to-price pass-through $M$ — whose product we call the **Spiral Gain**, $G = \Lambda \times M$. Third, an **Effective Wage Index**: a share-weighted index of everything that pays a household — market earnings, the statutory floor, indexed benefits, one-off handouts — deflated both by the published CPI and by a subsidy-neutral CPI reconstructed without the price-based support measures.

**A specification change, reported first because it removes two-thirds of the headline effect.** An earlier version of this paper pooled all seven countries onto one wage-equation coefficient vector with only fixed effects. That is not defensible and a Chow test rejects it decisively — $F = 2.87$ on $(120,\,1030)$, $p = 3.15\times10^{-19}$ — with own-lag persistence running from 0.967 in the United States to 0.222 in Italy. The specification here is **partially pooled**: every country keeps its own persistence, trend weight and slack response, and only the catch-up block and its interaction with $\lambda$ stay common, because $\lambda$ barely moves inside a country and the cross-section is the only place that effect can be identified. **Freeing the dynamics cuts the interaction by two-thirds, from +0.339 to +0.110.** Two-thirds of the apparent indexation effect was pooled-dynamics misspecification: a common persistence that fitted no country well, with the residual difference loading onto the one block that varied systematically across countries. A finding that does not survive its own specification check is not a finding, so we put this in the abstract, here, and in the results.

**What survives is the sign, and it survives everywhere.** The derivative $\partial\Lambda/\partial\lambda$ — the increase in the three-year recovery of a real-wage loss per unit of indexation intensity — is **positive in all seven countries, from +0.102 to +0.364**. An effect that vanished when the dynamics were freed would have been an artefact; one that shrinks but keeps its sign in every country is evidence about direction if not about size. The *level* of $\Lambda$ is a different matter and we do not treat it as comparable across countries: it is dominated by persistence, so the United States' $\Lambda(0) = -0.72$ reflects an own-lag sum of 0.967 rather than anything institutional.

Wage-to-price pass-through $M$ at three years is close to unity in the United States (0.968) and Italy (0.971), above it in the United Kingdom (1.386), lower in France (0.737), Germany (0.760) and Spain (0.689), and effectively zero in Belgium (−0.083). **The Spiral Gain is negative in all seven countries today**: no economy in the panel has a self-reinforcing loop, and none is near the threshold of one. The only positive cell anywhere in the table is Italy in 1975, at +0.028, under the *punto unico*.

Belgium is the case that disciplines the whole exercise and the case it leans on. It has the highest $\lambda$, at unity throughout, and an $M$ of −0.083: complete pass-through of prices into wages, none at all back out into prices. It is the only country whose $\Lambda$ is positive today (+0.084) and the only one whose $\partial G/\partial\lambda$ is negative (−0.015) — more indexation there buys more wage recovery and no more inflation. That is what Bernanke and Blanchard (2024) find directly — Belgian cumulative wage inflation of 17.8% against a euro-area 7.5%, with cumulative price inflation of 15.6% against 15.8% — and what the National Bank of Belgium reports from its own models, that "wages barely explain core inflation in Belgium" (Jonckheere and Zimmer 2024). An indexation regime is not automatically an inflation regime; whether it becomes one depends on the other factor in the product. Belgium is also the only country supplying in-sample observations anywhere near the top of the $\lambda$ range, so the same country that makes the result interpretable makes it fragile.

Finally, the Effective Wage Index shows measured real income for the bottom quartile tracking the all-household average to within a percentage point through 2022–24 in all four modelled countries, despite radically different income composition, because statutory floors and indexed benefits roughly kept pace with prices while market wages did not. The subsidy-neutral variant shows how much of the measured outcome was a statistical consequence of the delivery mechanism: for France, 2.4 index points at end-2022, reflecting a *bouclier tarifaire* worth about −2.6pp of HICP inflation in 2022 (Lemoine, Petronevich and Zhutova 2024).

We are explicit about what this exercise cannot deliver. There is no published series of any of these objects to validate against. The interaction block carrying the central claim has the right sign in sum and a significant fourth lag, but also a significant negative second lag. The standard errors are classical and computed on overlapping year-on-year observations, so they understate uncertainty. The elasticities converting coverage into $\lambda$ are calibrated, not estimated. The top of the $\lambda$ range is supplied by Belgium alone. These are not incidental caveats and they have their own section.

## Related literature

### Indexation theory and the spiral

The frame is Gray (1976) and Fischer (1977b). Gray's result is conditional: full indexation replicates the flexible-wage equilibrium and is optimal against nominal disturbances, but against real ones it blocks the real-wage adjustment the economy needs, and the optimal index parameter falls as the variance of real shocks rises. Fischer (1977b) states the corollary that matters here — indexing to the *consumer* price index means an imported energy shock, which requires a fall in the real consumption wage, is automatically resisted, converting a one-off relative price change into persistent inflation. Fischer (1977a) supplies the contracting foundation. Two qualifications travel with the frame: Jadresic (1996) shows that with realistic *lagged* indexation the conditional result does not survive, indexation destabilising output "regardless of whether shocks are nominal or real"; and Ball (1988) shows that costly, partial indexation is inefficient in equilibrium, so observed coverage should not be read as optimal.

Blanchard (1986) formalises the spiral as staggered wage and price decisions generating persistence. Blanchard and Galí (2007) supply the modern mechanism: real wage rigidity breaks the "divine coincidence" and generates a genuine inflation–output trade-off after supply shocks, and consumer-price indexation is precisely a device that produces it. Blanchard and Galí (2010) apply this to why the 2000s oil shocks were milder than the 1970s, concluding that all four candidate explanations mattered — good luck, lower oil intensity, more credible policy, less real wage rigidity. Gagliardone and Gertler (2023) give the sharpest quantitative version: a real wage rigidity parameter of 0.697, an oil–labour substitution elasticity of 0.37, and a fall in the marginal product of labour accounting for more than half of the rise in marginal cost. Modigliani and Padoa-Schioppa (1978) remain the reference for indexation above unity, which under Italy's 1975 *punto unico* applied to a large range of wages: any cost shock is then amplified through successive rounds, with no stable full-employment equilibrium without a fall in unit labour costs. That is the analytical ancestor of the condition $G > 1$ used below.

### How rare spirals actually are

The most important modern result for this paper is negative. Alvarez et al. (2024), from IMF Working Paper 2022/221, define an episode as at least three of four consecutive quarters with both accelerating consumer prices and rising nominal wages, find 79 such episodes across advanced economies since the 1960s, and show that only a small minority led to sustained acceleration; typically "inflation and nominal wage growth tended to stabilize, leaving real wage growth broadly unchanged". Where the starting point was falling real wages plus a tight labour market, inflation subsequently declined while nominal wage growth rose. The companion chapter (IMF 2022) identifies 22 prior episodes matching the 2021 configuration, finds no spirals followed, and estimates roughly 10% wage-to-services-price pass-through after five quarters and none to goods. Bernanke and Blanchard (2025) attribute most of the US surge to shocks to prices given wages; their multi-country extension (2024) finds "little evidence, in any economy, that a wage-price or price-wage spiral emerged", with catch-up coefficients close to zero in most countries. Lorenzoni and Werning (2023) reinterpret a spiral as equilibrium leapfrogging over a contested real pie rather than an unstable loop, and Shapiro (2024) documents that wage growth *lags* price growth and that labour-cost pass-through to core PCE is small and confined to services.

Against this stands the warning that is this paper's null hypothesis. Boissay, De Fiore, Igan, Pierres Tejada and Rees (2022) argue that relationships estimated on low-inflation samples are an unreliable guide, because sustained inflation may change wage-setting *institutions*, and the adoption of automatic indexation is the mechanism that would lock inflation into ongoing cycles. It was not borne out over 2022–25, but it is the right warning, and the reason to measure institutions rather than assume them. The ECB's 1970s-versus-today comparison (Battistini, Grapow, Hahn and Soudan 2022) states the contrast compactly: in the 1970s the wage share rose after the oil shock and real consumer wages strongly increased; after 2021–22 the wage share fell slightly and real consumer wages declined, with second-round effects "largely absent on average in the period since the euro was launched".

### Indexation regimes, country by country

The US COLA literature supplies the elasticity we calibrate on. Card (1986) estimates marginal indexation elasticities of 0.75–0.95 on 189 indexed contracts in Canadian manufacturing, 1968–75, and shows the degree of indexation rises with the co-movement of the industry's output price with the CPI — optimal risk-sharing, not mechanics. (He motivates with US COLA coverage but estimates on Canadian data.) Hendricks and Kahn (1983), on some 5,570 US union contracts over 1969–81, find that bargaining power and inflation uncertainty both raise the probability and strength of a COLA clause, and that wage inflation was higher under *uncapped* COLAs than under all others, with the gap widening in unanticipated inflation. Ehrenberg, Danziger and San (1983) synthesise the determinants and Ragan and Bratsberg (2000) is the reference on the decline; the coverage series comes from BLS (Lacombe and Borum 1987; BLS 1995).

The national episodes themselves — the Italian *scala mobile* and its dismantling (Modigliani and Padoa-Schioppa 1978; Manacorda 2004; Pastore 2010), the French sequence of 1981–83 (Sachs and Wyplosz 1986), the UK threshold agreements of 1973–74 (Bordo, Bush and Thomas 2025) and Belgian automatic indexation (Geis, Wong and Vernon 2023; Bijnens, Karimov and Konings 2023) — are set out with the institutional database below, where they are used, rather than twice.

### Did indexation come back?

It did not, at scale. Koester and Grapow (2021) give the pre-shock euro-area baseline: about 3% of private-sector employees under general automatic indexation, about 18% where inflation has a formal role in negotiations, about 18% with minimum-wage indexation only, more than half with no formal role, and automatic indexation concentrated in Belgium, Cyprus, Malta and Luxembourg. Górnicka and Koester (2023) find indexation clauses "rather infrequent" across the ECB wage tracker's seven countries, Spain excepted, and document the substitute: in Germany about 65% of agreements signed since 2021 included one-off payments averaging 64% of a monthly salary, against 24% before 2021. Bates, Bodnár, Healy and Roca I Llevadot (2025) conclude the euro area compensated through negotiation rather than formal indexation, with post-pandemic shocks accounting for around 3 percentage points of negotiated wage growth; Bates, Bodnár, Botelho and Rousseau (2025) put HICP-deflated compensation per employee about 5% below its 2021Q4 level in 2022Q4 and only about 0.5% below by 2025Q1; Bing, Holton, Koester and Roca I Llevadot (2024) report negotiated wage growth including one-offs rising from 1.4% in 2021 to 4.5% in 2023. De Spiegelaere (2023) and ILO (2024) document the Spanish revival in units that differ between them. Rodriguez Contreras and Molina (2023) find negotiated wages mostly grew slower than inflation across France, Germany and Italy, that minimum wage upratings played an "indirect but significant" role, and that "hardly any specific measures have influenced collective wage negotiations, except for the inflation allowance in Germany" — the sentence this paper's second and third angles are built on.

### Statutory floors and indexed benefits

This angle has a literature of its own, largely disconnected from the spiral literature, which is part of the point.

How much of a floor increase reaches workers above the floor determines how much of the wage bill a price-indexed floor actually indexes. Cengiz, Dube, Lindner and Zipperer (2019) bound it: wage gains extend to roughly \$3 above the new minimum and account for about **40% of the overall wage increase**, accruing to incumbents. Dube (2019) confirms the 40% share and notes that in US states with recent large increases more than half the increase comes from spillovers; Gopalan, Hamilton, Kalda and Sovich (2021) put the reach at up to \$2.50 above the minimum in payroll data. Autor, Manning and Smith (2016) enter the important dissent — they cannot reject that measured spillovers are reporting artefacts. Our `minwage` elasticity of 0.35 sits just below the central estimate and carries most of the modern French and British results, so the dissent matters; we return to it in the limitations.

How much comes back out as prices is the minimum-wage analogue of $M$. Lemos (2008) surveys the US evidence: a 10% increase raises food prices by no more than 4% and overall prices by no more than 0.4%. Point estimates cluster low — Aaronson (2001) and Aaronson, French and MacDonald (2008) find a 10% rise raising food-away-from-home prices about 0.7%, limited-service restaurants 1.55% against full-service 0.31%; Renkin, Montialoux and Siegenthaler (2022) find +0.36% on grocery prices, with adjustment in the three months after legislative *passage* rather than implementation; Leung (2021) estimates 0.06–0.08. Incidence estimates run higher: Harasztosi and Lindner (2019) find about 75% of the cost passed to consumers, Ashenfelter and Jurajda (2022) near-full pass-through in McDonald's franchise prices. MaCurdy (2015) draws the consequence that matters for the index built below: under full pass-through a minimum wage behaves like a value-added tax on consumer prices, more regressive than a typical state sales tax.

Aggregate magnitudes are small. The ECB (2022) puts the minimum-wage contribution to euro-area wage growth below 0.1pp per year over 2008–2018, rising to about 0.1–0.2pp in 2022 and 0.2–0.4pp in 2023. The Low Pay Commission (2026) estimates the 6.7% National Living Wage rise of April 2025 added roughly 0.06–0.24pp to the April 2025 inflation rate, and reports that minimum-wage jobs are about 6% of jobs but only about 2.5% of the weekly wage bill, while spillovers to the 35th percentile bring the NLW's reach to just under one-fifth of the economy-wide wage bill; the Bank of England's February 2026 *Monetary Policy Report* called the effect on overall wage growth "negligible". Glover and Mustre-del-Río (2021) connect this back to the loop: a doubling of the US federal minimum raises inflation about 2.5pp annualised under a fixed nominal rate but only about 1pp under the Taylor principle. The inflationary sign of a statutory wage floor is a monetary-policy choice, not a property of the floor.

On the benefit and public-pay side there is one indispensable source. Checherita-Westphal (2022) documents that automatic price indexation of public wages exists in only five euro-area countries — Belgium, Luxembourg, Cyprus, Malta and Italy — covering 19% of euro-area public wage expenditure and 18% of government employees, while public pensions are fully price-indexed in six countries covering 37% of pension expenditure, partially in ten more covering 33%, and wage-indexed in Germany and the Netherlands covering a further 30%; the magnitudes are a public wage bill of €922bn (7.6% of GDP) and public pensions of €1,484bn (12.1% of GDP) in 2021. Its panel estimates put the private wage reaction at 0.3–0.5pp per 1pp of public wage growth, the source of our `benchmark` elasticity and deliberately the bottom of that range. Directive (EU) 2022/2041 adds a supranational layer from 2022, with indicative reference values of 60% of the gross median and 50% of the gross average wage and updating at least every two years — or four where automatic indexation exists — making the minimum-wage channel, alone among the four, subject to an upward institutional ratchet. Wilcox (1989) established the awkward stylised fact that Social Security increases are announced at least six weeks ahead and yet consumption jumps on receipt: an argument for treating a benefit uprating as a genuine dated income impulse.

### Pass-through in both directions

The literature is unusually clear that the two directions behave differently. On wages to prices, Bernanke and Blanchard (2025) report a sum of coefficients on nominal wage growth of 0.665 in the US price equation with an implied long-run pass-through near unity; Haskel, Martin and Brandt (2023) find about 0.30 in the UK; Shapiro (2023) finds a 1pp rise in ECI growth raising the non-housing-services contribution to core PCE by 0.15pp over four years, so that labour costs explain roughly 0.1pp of the roughly 3pp rise in core PCE; Ampudia, Lombardi and Renault (2024) estimate euro-area sectoral pass-through at about 40% after eight quarters and 50% after three years, concentrated overwhelmingly in private services (up to 86%) rather than industry (35–40%); Hahn (2020) shows the price Phillips curve flattens in recessions while the wage Phillips curve is stable.

On prices to wages, the estimates are regime objects. Under automatic indexation the coefficient approaches the contractual elasticity — 0.75–0.95 in Card, about 0.96 for Italian industry, near-mechanical in Belgium. Without it, the estimated catch-up coefficient is statistically indistinguishable from zero in the US and in most of the eleven economies of Bernanke and Blanchard (2024), though the *cumulated* contribution can still be sizeable, as Haskel, Martin and Brandt (2023) show for the UK. A regime-dependent first leg and a market-structure-dependent second leg is the reason to write the spiral as a product.

### Modelling practice

We follow Bernanke and Blanchard (2025) in specification and depart in two places documented below. Their four-equation system — wage inflation, price inflation, short- and long-run expectations, estimated recursively with homogeneity restrictions making the long-run Phillips curve vertical — is the only fully written-out, publicly estimable, independently replicated wage–price system in the modern literature; the Banque de France replication (Aldama, Le Bihan and Le Gall 2024) confirms its portability.

The alternative traditions inform the details. Galí (2011) supplies the New Keynesian wage Phillips curve and indexation to a *four-quarter average* of price inflation, with estimated indexation coefficients of roughly 0.50–0.69; Galí and Gambetti (2020) show about half the apparent flattening of that curve disappears once the endogenous wage-markup component is purged — a caution against reading any single-equation slope as structural. FRB/US adopts the four-quarter device, crediting Galí, with a shipped indexation parameter of 0.6847 and a long-run attractor equal to trend inflation plus trend productivity growth (Brayton 2013); ECB-BASE writes the same attractor as $\bar\pi_t + \Delta\bar y_t$ (Angelini, Bokan, Christoffel, Ciccarelli and Zimic 2019); NAWM II carries separate indexation parameters on past price inflation and productivity growth (Coenen, Karadi, Schmidt and Warne 2018); COMPASS indexes to lagged *wage* rather than *price* inflation (Burgess et al. 2013). Our anchor is a fixed-gain local-level filter, the limiting case of Stock and Watson (2007). On the level-versus-difference question driving our main specification change, DeLuca and Van Zandweghe (2023) estimate a VECM whose error-correction term is on the *level* of the real wage.

### Handouts, subsidies and the mechanism by which a transfer becomes a price

Three literatures meet here. On the **accounting**, Sgaravatti, Tagliapietra, Trasi and Zachmann (2023) put national fiscal responses at €758.3 billion over September 2021 to January 2023 — €646bn in the EU, €103bn in the UK, €8bn in Norway — ranging from 7.4% of GDP in Germany to under 1% in Denmark, with 73% of household-directed funding untargeted; Sgaravatti, Tagliapietra and Trasi (2024) is the peer-reviewed version. Bańkowski et al. (2023) put euro-area discretionary support at about 2% of GDP in 2022 and again in 2023, about half affecting prices directly and only about 12% explicitly targeted; Ferdinandusse and Delgado-Téllez (2024) update it to 1.8% of GDP in 2022 and 1.3% in 2023 and confirm the targeted share stayed very low.

On the **statistical treatment**, which is what makes "de-facto income" measurable, Eurostat (2022) sets the rule and the UK applied identical logic in three classification statements (ONS 2022a, 2022b, 2022c); we set the rule out with the data below. The magnitudes are large: the OBR's November 2022 outlook put the Energy Price Guarantee at cutting the peak CPI inflation rate from 13.6% to 11.1%; Bourgeois and Lafrogne-Joussier (2022) estimate French inflation between 2021Q2 and 2022Q2 would have been 3.1 points higher without the shield; Lemoine, Petronevich and Zhutova (2024) give the through-time profile that is the single most useful number in this literature, −2.6pp on HICP inflation in 2022, +0.4pp in 2023, +1.0pp in 2024 and +0.8pp in 2025, cumulating to −0.4pp; Destatis (2022) attributes roughly a percentage point of CPI damping to the *Tankrabatt* and the 9-Euro-Ticket; Jannsen and Sonnenberg (2023) put the 2023 price brakes at about −0.8pp. Price measures move inflation through time; they do not remove it.

On the **mechanism by which the income half becomes a price**, Jordà, Liu, Nechio and Rivera-Reyes (2022) attribute about 3pp of US inflation by 2021Q4 to income transfers, cautioning that the estimate carries considerable uncertainty. di Giovanni, Kalemli-Özcan, Silva and Yıldırım (2023) find that removing government expenditure from the demand shock cuts predicted US inflation from 8.89pp to 5.91pp, and their companion paper (2022) establishes the state-dependence that matters most here: demand stimulus "would not have produced as high an inflation as the one observed" absent the sectoral supply shocks. Bianchi and Melosi (2022) attribute about half the surge to fiscal origins; Barro and Bianchi (2023) find a coefficient on composite government spending of 0.78 on headline CPI across 21 OECD economies with $R^2 = 0.79$ and note that the United States is not an outlier, cutting against the US-exceptionalism reading of Jordà et al.; Kindberg-Hanlon (2024) puts US Economic Impact Payments of about 4% of GDP at raising inflation by over a percentage point for several years. Against all of this sits Coibion, Gorodnichenko and Weber (2020), who find households spent only about 40% of the CARES Act transfer. Auclert, Rognlie and Straub (2024) make the theoretical point that a transfer's bite depends on the distribution of MPCs, which is why an untargeted handout is not the same object as a targeted one.

Orchard, Ramey and Wieland (2025) supply the mechanism that reconciles the tension, and it is the one this paper's fiscal block needs. Re-examining the 2008 US rebates, they find a corrected micro MPC of about 0.3 — higher than the survey estimates — but concentrated almost entirely in durables. Because the short-run supply curve for durables is steep, that concentrated demand shows up in the relative price rather than the quantity: the relative price of motor vehicles spiked about 1.0% in June 2008, and their preferred general-equilibrium consumption multiplier is about 0.06. A transfer paid to high-MPC households when the binding constraint is supply does not do what the micro MPC says it does; it becomes a price. That is why the price equation here carries a transfer term at all, and why the term is restricted to income-based measures; we take the implication up in the fiscal-loop section. Parker, Souleles, Johnson and McClelland (2013) give the benchmark micro estimate, an MPC of 12–30% on nondurables within three months; Dupor, Karabarbounis, Kudlyak and Mehkari (2023) supply the regional-to-aggregate bridge; de Soyres, Santacreu and Young (2022) put the aggregate outcome at about 2.5pp of US inflation from pandemic stimulus, with spillovers adding about 0.5pp to UK inflation.

On the **political economy**, Dornbusch and Edwards (1991) give the four-phase populist cycle — expansion, bottlenecks, inflation and shortages, collapse with real wages below the starting point — and the mechanism that populist programmes substitute administered prices and transfers for relative-price adjustment. Funke, Schularick and Trebesch (2023) supply modern cross-country evidence from 51 populist leaders over 1900–2020, with GDP per capita 10% lower after fifteen years than a synthetic counterfactual; the published abstract gives no inflation coefficient and we do not attribute one. Black, Liu, Parry and Vernon (2023) put explicit and implicit global fossil-fuel subsidies at \$7 trillion, 7.1% of global GDP, in 2022. On instrument choice, Komatsu (2025) finds caps in some euro-area countries added roughly 10pp of energy inflation and 0.5pp of headline inflation in the *uncapped* members in 2022, with the cooperative optimum no cap anywhere; Amores, Christl, De Agostini, De Poli and Maier (2023) give the two-sided microsimulation result that lump-sum transfers are more efficient per euro against the inequality effects of inflation while caps are more efficient against energy poverty specifically; and Hidalgo-Pérez, Collado Van-Baumberghen, Galindo and Mateo Escobar (2023) add the distributional counterpart for the Spanish gas cap, −0.3pp on headline inflation but −1.59pp for low-income households against −0.76pp for high-income ones.

## An institutional database of indexation

### The four channels

The database records, for each country and documented year, the share of employees whose pay moves through each of four channels: **automatic**, a contractual escalator moving pay with a price index by formula; **public**, statutory indexation of public-sector pay; **minwage**, pay set by or benchmarked to a price-indexed statutory floor; and **benchmark**, a formal, named role for inflation in collective bargaining.

The channels are deliberately not mutually exclusive — a French employee can be covered by a SMIC-benchmarked grid *and* by an agreement in which inflation has a named role; a Belgian public employee is covered by two channels. Coverage is recorded where documented, linearly interpolated between documented dates, held flat outside the documented range, and treated as zero before a channel's first documented date. Every row carries its source, and where a number is an arithmetic combination of two sourced numbers — typically union density times the COLA share among covered contracts — the derivation is recorded in the row. Interpolation is a modelling choice, not a measurement: institutions change on a date, but the *share of employees* affected drifts as contracts expire on a rolling basis. The one place this would actively mislead — the UK's 1974 threshold agreements, in force for a single year — is encoded as a step with adjacent zero rows so that it is not smoothed away.

### Constructing $\lambda$

The four coverage shares are collapsed into a single intensity by Eq. (W3): each channel's coverage is multiplied by a pass-through elasticity and the products summed and clipped to the unit interval. The elasticities are calibrated, not estimated:

| Channel | Elasticity $e_j$ | Calibration source |
|---|---:|---|
| automatic | 0.90 | Card (1986): marginal escalator elasticity 0.75–0.95 |
| public | 1.00 | statutory indexation of public pay is mechanical |
| minwage | 0.35 | Cengiz, Dube, Lindner and Zipperer (2019): spillovers about 40% of the total wage gain, extending to roughly \$3 above the floor |
| benchmark | 0.30 | Checherita-Westphal (2022), ECB Occasional Paper 299: private wage reaction of 0.3–0.5pp per 1pp of public wage growth |

Each is set at or below the central estimate in its source — 0.90 against Card's 0.75–0.95, 0.35 against the 40% spillover share, 0.30 at the bottom of Checherita-Westphal's 0.3–0.5 range. The bias is deliberately conservative, because an overstated elasticity would manufacture the paper's result. The `public` value of 1.00 is an accounting identity in the five euro-area countries where the statute is mechanical.

The clip at unity keeps $\lambda$ interpretable as "the fraction of the wage bill that moves one-for-one with past prices", and it binds in two countries. Belgium is at the clip throughout: automatic coverage of 0.960 at elasticity 0.90 plus public coverage of 0.180 at 1.00 sums to 1.044 before clipping. Italy is at the clip during the *scala mobile* years: 0.960 automatic plus 0.140 public gives a raw 1.004 — the arithmetic counterpart of Modigliani and Padoa-Schioppa's observation that Italian indexation exceeded 100% for a large part of the wage distribution, and the point at which our construction, capped at one, stops being able to represent what was happening. Nowhere else does the sum approach unity.

One further point bears on what $\lambda$ measures. Indexing a wage floor does not merely change its path; it changes behaviour around it. Brummund and Strain (2020) find the immediate disemployment effect of a minimum-wage increase in an indexing state about three times that of an equivalent nominal increase elsewhere, presumably because an automatic increase is understood to be permanent while a discretionary one may be eroded. A given coverage share therefore carries more behavioural content where the rule is automatic than where it is discretionary — an argument for entering $\lambda$ as an interaction in Eq. (W4) rather than treating coverage as a scaling factor.

### The $\lambda$ table

| country | 1965 | 1975 | 1985 | 1995 | 2005 | 2015 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|
| US | 0.050 | 0.112 | 0.079 | 0.032 | 0.014 | 0.017 | 0.019 |
| UK | 0.106 | 0.120 | 0.088 | 0.063 | 0.076 | 0.078 | 0.102 |
| FR | 0.359 | 0.370 | 0.279 | 0.244 | 0.242 | 0.238 | 0.236 |
| DE | 0.112 | 0.107 | 0.092 | 0.066 | 0.052 | 0.064 | 0.070 |
| BE | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| IT | 0.668 | 1.000 | 0.534 | 0.320 | 0.320 | 0.320 | 0.320 |
| ES | 0.000 | 0.000 | 0.000 | 0.000 | 0.150 | 0.042 | 0.150 |

Three features of this table carry the paper. The cross-sectional range at any date is an order of magnitude wider than the time-series range within any country. The United States moves from 0.112 to 0.019 across sixty years, a factor of six, but never leaves the bottom of the distribution. Belgium never moves. And Italy traverses almost the whole range within twenty years — though, as the data and results sections set out, that traverse happens almost entirely before the Italian estimation sample opens, so it is a fact the database records rather than variation the regression uses.

Two conventions in the table should be stated rather than inferred. Coverage is zero, not missing, before a channel's first documented date: Spain's wage-guarantee clauses are documented only from 2000, so Spanish $\lambda$ reads zero for the four earlier columns, which means "no documented coverage" and not "verified absence". And the table samples 1 January of each year, which is why it misses events lasting less than a year.

The sharpest single event is one of those. The UK's threshold agreements were in force through 1974 only, so the 1975 column shows 0.120 rather than the peak. On the coverage shares and elasticities above, UK $\lambda$ reaches **0.416** in 1974Q1 — the automatic channel contributing $0.330 \times 0.90 = 0.297$ and the benchmark channel about 0.119 — decaying through the year as contracts rolled off. That figure is the UK's in-sample maximum and the second-highest observation anywhere in the estimation sample outside Belgium. The model's validation suite checks precisely this: UK $\lambda$ must peak in 1974 and nowhere else.

### Country narratives

**United States: the COLA decline.** The automatic channel is union density times the COLA share among workers under major agreements. Coverage rises from 0.056 in 1960 (density 0.28 times a COLA share of about 0.20) to a peak of 0.138 over 1976–80 (0.230 times 0.60) — at an elasticity of 0.90, a $\lambda$ contribution of 0.124, the US maximum anywhere — then falls with both factors together: 0.088 in 1985, 0.070 in 1986, 0.047 in 1991, 0.037 in 1993, 0.035 in 1995 when the BLS programme was discontinued, after which the database carries an assumed decay to 0.005 by 2026. Ragan and Bratsberg (2000) is the authority for the direction; nobody is the authority for the level. The minimum-wage channel is identically zero until Washington's Initiative 688 of 1998, the first state indexing law, then rises with the indexing states — 0.004 in 2000, 0.010 in 2005, 0.026 in 2010 after the 2006 ballot wave, 0.038 in 2022 with thirteen states plus DC, 0.041 by 2026. The public channel is zero: FEPCA 1990 ties federal pay to the ECI, but the formula is routinely overridden and is a wage link, not a price link.

**United Kingdom: the 1974 thresholds and the floor that replaced them.** The automatic channel is zero except in 1974, at 0.330 — Stage 3 of the Heath pay policy, announced 3 October 1973, triggered once the RPI rose 7% above base, covering roughly a third of the workforce and firing eleven times in twelve months (Bordo, Bush and Thomas 2025). The benchmark channel declines with bargaining coverage, from 0.330 in 1960 through a peak of 0.400 in 1975 to 0.130 by 2026 (coverage about 0.26 times a weight of 0.5). What arrests the decline in $\lambda$ from 2016 is the statutory floor: a first NMW rate in April 1999 covering about 6% of jobs, the National Living Wage from April 2016 raising coverage to 0.10, and spillover estimates putting the effective reach at about 0.17 of the wage bill by 2021 and 0.18 by 2026 — minimum-wage jobs are about 6% of jobs but only 2.5% of the weekly wage bill, and spillovers to the 35th percentile bring the reach to just under one-fifth of it (Low Pay Commission 2026). UK $\lambda$ is therefore *higher* in 2024 (0.102) than in 1995 (0.063), for statutory rather than contractual reasons.

**France: the 1983 *désindexation* that left the SMIC alone.** Ordonnance 58-1374 of 1958 prohibited indexation on the general price level — confirmed in Code monétaire et financier art. L112-2 — with an explicit exception for the SMIG, so the automatic channel is zero throughout. The benchmark channel, standing for the *échelle mobile* norm, sits at 0.700 until the June 1982 *blocage*, falls to 0.400 in 1984 after the *tournant de la rigueur*, to 0.250 by 1990 and 0.180 from 2021. The minimum-wage channel does the opposite: the SMIG was indexed by the law of 18 July 1952, and the law of 2 January 1970 created the SMIC, whose formula — now Code du travail arts. L3231-4 and L3231-5 — sets the annual revalorisation equal to the consumer price index for first-quintile households plus half the gain in the purchasing power of the basic hourly wage, with an automatic mid-year trigger at a cumulative 2% and a discretionary *coup de pouce* on top. That channel rises from 0.400 in 1960 to 0.450 in 1970, 0.500 by 2000 — France is the country the ECB names on minimum-wage indexation — and 0.520 from 2021, with 17.3% of employees at the SMIC on 1 January 2024, the SMIC at 62.5% of the median wage, and nine revalorisations between end-2020 and end-2024, four automatic. The public channel is zero, on Checherita-Westphal's (2022) five-country list: the *point d'indice* is discretionary and was frozen over 2010–2016 and 2017–2021. The validation suite tests exactly this — the French minimum-wage channel must not fall after 1983 — and because it did not, French $\lambda$ falls from 0.370 in 1975 only to 0.236 in 2024: a decline of 36%, against 83% for the United States and 68% for Italy, but slightly more than Germany's 35% and 2.4 times the United Kingdom's 15%. France is mid-pack in the *rate* of decline and, among the four modelled countries, first in the *level* — Belgium at 1.000 and Italy at 0.320 are both higher — because the floor held while the bargain did not.

**Germany: absence, and its substitute.** The automatic and public channels are zero throughout, the latter again on Checherita-Westphal (2022). The benchmark channel tracks *Tarifbindung* with a weight that itself changes: 0.380 in the 1960s–70s (coverage about 0.85 times a weight of 0.45), 0.350 in 1980, then 0.220 in 1995, 0.150 in 2010 and 0.130 from 2022 (coverage about 0.43 times 0.30). The database records the weight change explicitly — 0.45 before 1990, 0.30 after — on the ground that the share of covered employees for whom inflation had a *named* role fell with the shift from Bundesbank-era norm-setting to the post-1995 framework. It is a judgement, and it flatters the pre-1990 numbers. The minimum-wage channel does not exist before 2015: the *Mindestlohngesetz* took effect on 1 January 2015 at €8.50, and the statutory rise to €12.00 on 1 October 2022, by legislation bypassing the *Mindestlohnkommission*, sharply raised the bite. Under MiLoG s.9 the Commission decides every two years under a backward-looking orientation to the collectively agreed wage index, so the German rule is a lagged peg to negotiated wages, not to prices, and its contribution to $\lambda$ is a coverage effect rather than an indexation effect in the strict sense.

Germany is where indexation was substituted for rather than adopted. The *Inflationsausgleichsprämie*, up to €3,000 free of income tax and social contributions, payable 26 October 2022 to 31 December 2024, reached 86.3% of collectively-agreed employees at an average of €2,680 — full coverage at the maximum in public administration, against 11.6% in hospitality and an average of €1,103 in construction (Destatis 2025). It is tax-privileged, concentrated in the public sector and unionised manufacturing, invisible in the CPI, present in measured negotiated wages, and delivers a one-off top-up without entering the permanent wage base: precisely the design objective of a country that does not want an escalator. It is also a measurement problem we cannot fully solve.

**Belgium: the system that never stopped.** Coverage of 0.960 on the automatic channel and 0.180 on the public channel — the latter the share of *all* employees who are public employees, not the share of public employees who are indexed — puts Belgian $\lambda$ at the clip throughout. Indexation runs off the health index and, in most of the private sector and all of the public sector, its smoothed four-month average; roughly half of private-sector employees are on a 2% pivot trigger and about 40% index annually in January, and the 1996 Wage Law caps real wage growth by reference to France, Germany and the Netherlands (Geis, Wong and Vernon 2023). The discretionary suspensions (*saut d'index*) of the 1980s and 2015–16 are one-off level events rather than regime changes, and we do not encode them as coverage reductions.

**Italy: the *scala mobile* and its dismantling.** The automatic channel is 0.400 before 1975, 0.960 from 1975 to 1983 under the *punto unico*, 0.500 from 1984 after the *decreto di San Valentino*, and zero from 1992. The benchmark channel takes over at 0.600 from 1993 with the Protocol's forward-looking concertation, benchmarked to ISTAT's three-year forecast of consumer prices excluding imported energy rather than to realised inflation — an important distinction, since a forward-looking index is not a catch-up device at all. Italy also indexes public pay, one of Checherita-Westphal's five countries, with public employment about 14% of the total, contributing 0.140 throughout. Italian $\lambda$ therefore traverses from 0.668 in 1965 to 1.000 in 1975 to 0.320 from 1995: the largest traverse in the database, and not identifying variation, because the Italian estimation sample begins 1985Q4.

**Spain: collapse and partial revival.** The benchmark channel stands at 0.700 in 2000 on the estimate that wage-guarantee clauses covered over 70% of workers in the early 2000s, falls to a trough of 0.140 over 2014–21, and rebounds to 0.500 from 2023 on the ILO's report that about half of employees under agreements in force in 2023 had indexation mechanisms. Two weaknesses: Spanish coverage before 2000 is undocumented and therefore reads 0.000 under the database's no-back-filling rule, which is certainly wrong as a description of Franco-era and transition-era Spain and should be read as missing data recorded as zero; and the 2022–23 revival figures come from two sources reporting in different units, which we have not reconciled against the primary MITES statistics.

## Model

The system is quarterly. Growth rates are year-on-year log changes in percent, $100 \times [\log x_t - \log x_{t-4}]$, throughout; the reason is a data constraint discussed in the next section rather than a modelling preference. Estimation is least squares with at most one linear restriction imposed analytically, so that the whole estimator can be reproduced exactly in a browser implementation; standard errors are classical.

### Trend inflation

The expectations anchor is a fixed-gain local-level filter:

$$\pi^{*}_{t} \;=\; \pi^{*}_{t-1} \;+\; k(q)\,\bigl(\pi_{t} - \pi^{*}_{t-1}\bigr),
\qquad k(q) = \frac{\sqrt{q^{2}+4q}\;-\;q}{2} \tag{W1}$$

where $q$ is the signal-to-noise ratio of a random-walk-plus-noise model for inflation. $q \to 0$ gives $k = 0$, a constant trend and perfectly anchored expectations; $q \to \infty$ gives $k \to 1$ and no anchor at all. This is the fixed-gain limit of the Stock–Watson (2007) unobserved-components model with stochastic volatility, chosen over the full version because a single gain is one readable number. The baseline is $q = 0.05$, which gives $k = 0.20$ exactly. The filter is initialised at the mean of the first four observations, so no future information enters.

$\pi^{*}$ plays the role of Bernanke and Blanchard's short-run expectations term $gexp$, and the anchoring parameter $q$ plays the role of their $\gamma$, with the difference that ours is a calibrated dial rather than an estimated coefficient.

### The catch-up term, and why it is not Bernanke and Blanchard's

Bernanke and Blanchard's catch-up regressor is realised four-quarter inflation minus the one-year-ahead survey expectation formed four quarters earlier:

$$\text{catchup}^{BB}_{t} \;=\; \pi^{\text{yoy}}_{t} \;-\; \pi^{*}_{t-4} \tag{W2$'$}$$

We retain this object for reference but do not use it, and the reason is a genuine methodological point rather than a convenience. Their term relies on a *survey* expectation, which is an independent data series. Outside the United States the survey is unavailable over most of the sample, and the natural substitute is to difference realised inflation against the filtered trend. That substitution is fatal. With a fixed-gain filter, the trend's own recursion can be inverted:

$$\pi_{t} \;=\; \pi^{*}_{t-1} \;+\; \frac{\pi^{*}_{t} - \pi^{*}_{t-1}}{k}$$

so realised inflation is an exact linear function of current and lagged values of the trend. The catch-up block and the trend block then span the same space, and the regression is singular in the limit and explosive near it. In our panel the symptom was unmistakable: catch-up coefficients of $+54$ at a gain of $k = 0.20$ — that is, $1/k$ times noise.

We therefore replace it with a one-sided real-wage gap. Let $rw_t = 100\log(W_t/P_t)$ be the log real wage. For each $t$, fit $rw = a + b\,\tau$ by least squares on the 40 observations *ending at $t-1$*, project one period forward, and define

$$\text{catchup}_{t} \;=\; -\bigl(rw_{t} - \hat{a}_{t} - \hat{b}_{t}\,t\bigr) \tag{W2}$$

The term is positive when the real wage has fallen below the trend it was on — the state in which workers have something to catch up. Nothing dated after $t$ enters, so the series can be computed in real time. A trailing moving average would do the same job badly: real wages trend, a centred window is unavailable at the sample end, and an MA gap therefore inherits a bias of half the window's drift; projecting the fitted trend removes it.

The cost of this substitution is real and we state it plainly: the coefficient is no longer comparable with Bernanke and Blanchard's Table 1, and the validation exercise against their published numbers is correspondingly weakened. The gain is a coefficient that means something, and a specification that the theoretical literature actually describes. Bernanke and Blanchard's own structural Eq. (2) has wages chase an *aspiration real wage*, a level object; DeLuca and Van Zandweghe (2023) make the same argument in favour of an error-correction term on the level of the real wage. Our term is the one-sided, real-time version of that error correction.

### Indexation intensity

$$\lambda_{t} \;=\; \min\Bigl\{\,1,\; \sum_{j \in \{\text{auto, pub, mw, bench}\}} c_{j,t}\, e_{j}\,\Bigr\} \tag{W3}$$

with $c_{j,t}$ the coverage share of channel $j$ from the institutional database and $e_j$ the calibrated elasticities of the table above. Missing channels count as zero coverage, so a country with no minimum wage in a given era contributes nothing rather than breaking the construction.

### The wage equation

The estimated wage equation, for a single country, is

$$
\begin{aligned}
gw_{t} \;=\;& a_{0}
  \;+\; \sum_{k=1}^{p} a_{k}\, gw_{t-k}
  \;+\; \sum_{k=1}^{p} b_{k}\, \pi^{*}_{t-k}
  \;+\; \sum_{k=1}^{p} c_{k}\, x_{t-k} \\[2pt]
 &+\; \sum_{k=1}^{p} d_{k}\, \text{catchup}_{t-k}
  \;+\; \sum_{k=1}^{p} \tilde{d}_{k}\, \bigl[\lambda_{t-k}\,\text{catchup}_{t-k}\bigr] \\[2pt]
 &+\; e_{1}\, gpty_{t-1} \;+\; f_{1}\, dmw_{t} \;+\; u_{t}
\end{aligned}
\tag{W4}
$$

subject to $\sum_k a_{k} + \sum_k b_{k} = 1$, with $p = 4$, $x_t$ labour-market tightness, $gpty$ trend productivity growth and $dmw$ minimum-wage growth. The restriction makes the long-run Phillips curve vertical, as in Bernanke and Blanchard.

The catch-up block enters **twice**: at its own level, and multiplied by $\lambda_t$. The level coefficients $d_k$ are the pass-through of a real-wage loss in a country with no indexation at all; the interaction coefficients $\tilde{d}_k$ are the additional pass-through per unit of intensity. The test that matters is $\sum_k \tilde{d}_k > 0$. Setting $\tilde{d}_k \equiv 0$ recovers a constant-coefficient specification of exactly the Bernanke–Blanchard form.

The headline estimate is the panel version, and it is **partially pooled**. Every country $c$ keeps its own persistence, trend weight and slack response; the catch-up level and its interaction with $\lambda$ are common:

$$
\begin{aligned}
gw_{c,t} \;=\;& \alpha_{c}
  \;+\; \sum_{k=1}^{p} a_{c,k}\, gw_{c,t-k}
  \;+\; \sum_{k=1}^{p} b_{c,k}\, \pi^{*}_{c,t-k}
  \;+\; \sum_{k=1}^{p} c_{c,k}\, x_{c,t-k} \\[2pt]
 &+\; \sum_{k=1}^{p} d_{k}\, \text{catchup}_{c,t-k}
  \;+\; \sum_{k=1}^{p} \tilde{d}_{k}\, \bigl[\lambda_{c,t-k}\,\text{catchup}_{c,t-k}\bigr]
  \;+\; u_{c,t}
\end{aligned}
\tag{W4$'$}
$$

subject to one homogeneity restriction **per country**, $\sum_{k} a_{c,k} + \sum_{k} b_{c,k} = 1$ for each $c$, which is why the estimator takes a restriction *matrix* rather than a single vector. Country fixed effects absorb the level of each country's average wage growth. The productivity and minimum-wage-growth terms are dropped, being unavailable on a consistent basis across all seven countries.

**Why the middle of three choices.** Pooling everything — one coefficient vector with only fixed effects, which an earlier version of this paper estimated — is not credible: wage-setting in Belgium, where half the private sector sits on a pivot-index trigger, and in the United States, where almost nobody does, are not the same process, and an estimator that says they are will attribute to the catch-up term whatever the common persistence gets wrong. The next subsection shows it does, and by how much. Freeing everything is the opposite failure: $\lambda$ barely moves inside a country — constant in Belgium, 0.014 to 0.124 across sixty-five years in the United States, 0.236 to 0.274 in France — so a country-by-country catch-up interaction is identified off almost no variation and returns noise. The whole reason the reference countries are in the panel is that $\lambda$ varies *across* them. The split therefore follows the economics: the parts that differ by country because labour markets differ are free, and the one parameter the paper is about is common, because the cross-section is the only place variation exists to identify it. It is a restriction, we state it as one, and the mean-group estimates below are the fully heterogeneous alternative.

One consequence matters for everything that follows: because each country keeps its own persistence, **the three-year catch-up $\Lambda$ is country-specific even though the catch-up coefficients are common**. The same impulse propagates differently through different dynamics, so $\Lambda$ is a family of seven lines rather than one.

**Identification.** The interaction is identified across the panel or not at all, and where in the panel matters. Across the estimation sample $\lambda$ runs from 0.000 (Spain before 2000, where no coverage is documented) to 1.000 (Belgium). The dense region is $[0, 0.3]$: the United States, Germany, Spain and France all live there. Above 0.3 there are exactly three sources — the United Kingdom's 1974 threshold episode at 0.416, inside the sample, which begins 1973Q4; Italy at 0.492 in the mid-1980s; and Belgium at exactly 1.000 for all 101 of its quarters. Inside the estimation sample there is nothing at all between 0.5 and 1.0. The sharpest cross-country contrast remains Belgium against Germany — two economies sharing a currency, a central bank, a broadly common trade structure and, in 2022, the same energy shock, differing in exactly the institution under study, $\lambda = 1.000$ against $\lambda = 0.069$ — but because Belgian $\lambda$ never moves, that contrast enters only through the interaction.

Italy does **not** supply the within-country traverse one would want. Its *scala mobile* years, when $\lambda$ was at the clip, lie outside the estimation sample: the Italian panel begins 1985Q4, after the 1984 *decreto di San Valentino*, and its in-sample $\lambda$ runs 0.140 to 0.492. The dismantling of the *scala mobile* is a fact the database records and the figures display; it is not variation the regression sees.

### Poolability: is one coefficient vector defensible?

It is not, and the test is part of the method rather than an appendix note, because the answer changes the paper's central number.

`poolability_test` runs a Chow-style $F$-test of the fully pooled wage equation against the fully heterogeneous one, both with country fixed effects:

$$F \;=\; \frac{(\text{SSR}_{\text{pooled}} - \text{SSR}_{\text{free}})/q}{\text{SSR}_{\text{free}}/(n - k_{\text{free}})}$$

On this panel it returns **$F = 2.87$ on $(120,\,1030)$, $p = 3.15 \times 10^{-19}$**, with $R^{2}$ rising from 0.840 fully pooled to 0.880 fully free. Pooling is rejected about as decisively as a specification test can reject anything.

The economics behind the rejection is visible in one column of the results below. Own-lag persistence, the sum $\sum_k a_{c,k}$, runs from **0.967 in the United States to 0.222 in Italy**. These are not small differences around a common value; they are different processes. A US wage equation is close to a random walk in the four-quarter growth rate, an Italian one is not, and imposing one persistence on both forces the residual difference into whichever regressor can absorb it. In the fully pooled specification that regressor was the catch-up block — which is exactly the block the paper is about.

A rejection says the pooled slopes are wrong; it does not say every slope must be freed. We free the three the test rejects pooling on and keep common the one that identification requires, for the reasons set out above.

### The price equation

$$
\begin{aligned}
gp_{t} \;=\;& \beta_{0}
  \;+\; \sum_{k=1}^{p} B_{k}\, gp_{t-k}
  \;+\; \sum_{k=0}^{p} M_{k}\, gw_{t-k}
  \;+\; \sum_{k=0}^{p} E_{k}\, grpe_{t-k} \\[2pt]
 &+\; \sum_{k=0}^{p} F_{k}\, grpf_{t-k}
  \;+\; \sum_{k=0}^{p} P_{k}\, h_{t-k}
  \;+\; B_{m}\, gpty_{t-1} \;+\; v_{t}
\end{aligned}
\tag{W5}
$$

subject to $\sum_k B_k + \sum_k M_k = 1$. Relative energy and food prices $grpe$, $grpf$ are measured against **wages**, not against the headline index — Bernanke and Blanchard's own convention, which makes them real-product-wage terms, and the commonest error in replications of their work.

There are two deliberate departures. The first is the term $h_t$: the **income-based** fiscal support impulse, cash transfers and one-off payments to households expressed as a change in the share of household disposable income. Bernanke and Blanchard have no fiscal block; this is the term through which a government's response to an energy shock feeds back into prices. The second is what is deliberately excluded from it: price-based support — tariff shields, fuel-duty cuts, subsidised transport fares — does not add demand, subtracts mechanically from the measured index, and is handled instead as a CPI wedge in the effective-wage block.

### The Spiral Gain

Define the response of a scalar autoregression to a permanent unit step in a driver,

$$y_{t} \;=\; \sum_{k=1}^{p} \rho_{k}\, y_{t-k} \;+\; \sum_{k=0}^{q} \theta_{k}\, z_{t-k},
\qquad z_{t} = 1 \;\text{for}\; t \ge 0$$

and write $\mathcal{C}(\rho, \theta; H) = y_{H-1}$. The **price-to-wage gain** is

$$\Lambda_{c}(\lambda) \;=\; \mathcal{C}\Bigl(\{a_{c,k}\},\; \bigl\{0,\; d_1 + \lambda \tilde{d}_1,\; \dots,\; d_p + \lambda \tilde{d}_p\bigr\};\; 12\Bigr) \tag{W6}$$

the three-year cumulative response of wage growth to a permanent 1pp rise in realised inflation at intensity $\lambda$. It carries a country subscript because the catch-up coefficients $d$, $\tilde{d}$ are common but the dynamics $a_{c}$ they propagate through are not, so the same impulse produces a different three-year response in a labour market with an own-lag sum of 0.97 and one with 0.22. The **wage-to-price gain** is

$$M \;=\; \mathcal{C}\Bigl(\{B_k\},\; \{M_0, \dots, M_p\};\; 12\Bigr) \tag{W7}$$

and the **Spiral Gain** is the product:

$$G_{c,t} \;=\; \Lambda_{c}(\lambda_{c,t}) \times M_{c} \tag{W8}$$

$G > 1$ is the spiral condition: one turn of the loop more than reproduces itself within three years, so the shock is self-sustaining without further impulse.

Three choices need defending. First, the **horizon**. The natural object is the long-run multiplier $\sum \theta / (1 - \sum \rho)$, but homogeneity makes it uninformative by construction: imposing $\sum B + \sum M = 1$ sets the price equation's long-run wage pass-through to exactly one whatever the data say, because that is the assumption of a vertical Phillips curve. The restriction is right, but it means the long run cannot be where regimes differ. Three years can: it is where the euro-area sectoral pass-through literature reports its estimates (Ampudia, Lombardi and Renault put wage-to-price at about 40% after two years and 50% after three), long enough for an indexation clause to fire several times, short enough that monetary policy has not undone the shock.

Second, $\Lambda$ reads only the catch-up channel and holds $\pi^{*}$ fixed. A permanent 1pp rise in inflation also moves the trend, but that is the *expectations* route and is common to every regime; what distinguishes 1975 from 2023 is the catch-up route, and the two are added back together in the simulator.

Third, $M$ is estimated once per country and held constant, so time variation in $G$ is entirely institutional — which is the point: the claim being tested is that what changed between the 1970s and 2020s is who is indexed, not how firms price. A rolling-window variant in which both gains move is the honest robustness check.

The fiscal route enters additively on the first leg:

$$\Phi \;=\; \varphi_{e} \cdot \text{mpc} \cdot \mathcal{C}\bigl(\{B_k\},\, \{P_0,\dots,P_p\};\, 12\bigr),
\qquad G^{\text{fiscal}}_{t} \;=\; \bigl[\Lambda(\lambda_t) + \Phi\bigr]\times M \tag{W8b}$$

with $\varphi_e$ the transfer response to a one-point inflation shock, in percent of household disposable income, and $\text{mpc}$ the share reaching demand.

### The fiscal reaction function

$$
h_{t} \;=\; \rho\, h_{t-1} \;+\; \varphi_{e}\, \text{energyshock}_{t}
\;+\; \varphi_{\pi}\bigl(\pi_{t} - \pi^{*}_{t}\bigr)
\;+\; \varphi_{x}\, x_{t} \;+\; \varphi_{P}\, \text{populist}_{t}
\;+\; \alpha_{i} \;+\; \varepsilon_{t}
\tag{W9}
$$

estimated on the pooled panel with country fixed effects. $\varphi_P$ is the coefficient the policy discussion turns on: the extra transfer response associated with a populist executive, over and above the response to the shock itself.

### The Effective Wage Index

$$\text{EWI}_{t} \;=\; \sum_{c \,\neq\, \text{handout}} \frac{s_{c}}{\sum_{c' \neq \text{handout}} s_{c'}}\; X_{c,t}
\;+\; \bigl(X_{\text{handout},t} - 100\bigr) \tag{W10}$$

where the components $X_c$ are level indices, each 100 in 2019Q4: `wage` (market earnings), `minwage` (the statutory floor), `benefit` (indexed social benefits and public pensions, built from the statutory uprating rule rather than from spending), and `handout` (one-off payments and income-based energy support).

The asymmetry is deliberate. The three recurring sources are weighted by their share of income — market earnings are 42% of the bottom quartile's income in the United States, so a 10% raise is worth 4.2 index points — and the three weights are renormalised to one. A one-off payment has no share, because it is a flow that exists in one year and not the next; its component index is one plus the payment as a fraction of household disposable income, so $X_{\text{handout}} - 100$ is *already* the payment measured in index points, and weighting it again by a notional one per cent "handout share" would shrink a €300 *Energiepreispauschale* to a rounding error. The composition tables carry a `handout` column for completeness; the index does not use it as a weight.

Deflation is done twice:

$$\text{REWI}_{t} \;=\; \frac{\text{EWI}_{t}}{P_{t}},
\qquad
\widetilde{\text{REWI}}_{t} \;=\; \frac{\text{EWI}_{t}}{\tilde{P}_{t}},
\qquad
\tilde{P}_{t} \;=\; P_{t}\exp\Bigl(-\tfrac{1}{400}\textstyle\sum_{s \le t} \omega_{s}\Bigr)
\tag{W11}
$$

where $\omega_s$ is the estimated contribution, in percentage points of year-on-year inflation, of price-based support measures — negative while a shield is in force, positive as it unwinds. $\text{REWI}$ is what a statistician sees; $\widetilde{\text{REWI}}$ is what households would have faced had the same money been delivered as income. The gap is the part of measured real income that is a consequence of the delivery mechanism rather than of what households received.

### The simulator

$$
\begin{aligned}
gp_{t} &= \textstyle\sum_k B_k\, gp_{t-k} + \sum_k M_k\, gw_{t-k} + \sum_k E_k\, grpe_{t-k} + \sum_k P_k\, h_{t-k}\\
gw_{t} &= \textstyle\sum_k a_k\, gw_{t-k} + \sum_k b_k\, \pi^{*}_{t-k} + \sum_k c_k\, x_{t-k} + \sum_k \bigl(d_k + \lambda\tilde{d}_k\bigr)\,\text{catchup}_{t-k}\\
\pi^{*}_{t} &= \pi^{*}_{t-1} + k(q)\bigl(gp_t - \pi^{*}_{t-1}\bigr)\\
rw_{t} &= rw_{t-1} + \tfrac{1}{4}\bigl(gw_t - gp_t\bigr)\\
\text{catchup}_{t} &= -\,rw_{t}\\
h_{t} &= \varphi_{e}\cdot \max\bigl(gp_t - \pi^{*}_t,\,0\bigr)\cdot \text{mpc}\\
x_{t} &= -\,\tau\,\bigl(gp_t - \pi^{*}_t\bigr)
\end{aligned}
\tag{W12}
$$

Two features of this system deserve comment. The first is the catch-up line, which must be, and now is, the same object the coefficients were estimated on: the deviation of the log real wage from its trend, in percent. An earlier version of the simulator drove it with the Bernanke–Blanchard inflation surprise — the very object the specification section rejects — which fed coefficients estimated on a level gap a regressor measured in inflation differences. Different units, different scale, and every simulated path wrong. In a deviation-from-baseline simulation the trend real wage *is* the baseline, so the gap is simply the cumulated real-wage shortfall; since $gw$ and $gp$ are four-quarter rates, one quarter contributes a quarter of the annual rate, which is the $\tfrac{1}{4}$ in the $rw$ recursion.

The second is the monetary rule, written as a direct slack response rather than as an interest-rate rule. The estimated wage equation takes slack, not the policy rate, so a Taylor rule would require an IS curve we have not estimated; $\tau$ is therefore a reduced-form sacrifice-rate dial, "percentage points of slack opened per percentage point of inflation above trend". The handout rule is one-sided: governments hand out money when inflation is above trend and do not claw it back when inflation is below.

## Data

### Country samples

Seven countries. The four **modelled** economies are the United States, the United Kingdom, France and Germany; the three **reference** economies are Belgium, Italy and Spain. The reference countries are not the paper's subject but they carry most of the cross-sectional range in $\lambda$, without which the interaction would be identified only off time series in which $\lambda$ never exceeds 0.124 (the US), 0.416 for a single year (the UK), 0.274 (France) or 0.071 (Germany).

What matters is not the nominal start but the quarters each country actually contributes once every regressor is present:

| Country | Estimation sample | Obs. | $\lambda$ min | $\lambda$ max |
|---|---|---:|---:|---:|
| US | 1961Q1 – 2026Q2 | 262 | 0.014 | 0.124 |
| UK | 1973Q4 – 2026Q2 | 211 | 0.058 | 0.416 |
| FR | 1985Q4 – 2026Q1 | 162 | 0.236 | 0.274 |
| DE | 1993Q4 – 2026Q1 | 130 | 0.043 | 0.071 |
| BE | 2001Q1 – 2026Q1 | 101 | 1.000 | 1.000 |
| IT | 1985Q4 – 2026Q1 | 162 | 0.140 | 0.492 |
| ES | 1989Q1 – 2026Q1 | 149 | 0.000 | 0.210 |

The rows sum to 1177, the regression's $n$ exactly; they are counted off its own design matrix.

Three consequences are load-bearing. The **United States** carries the historical identification, as the only country contributing through the 1960s and 1970s and the one whose COLA episode is documented at contract level. The **United Kingdom** sample begins 1973Q4 and therefore contains the threshold agreements, which is why its in-sample maximum of 0.416 is the third-highest in the panel, behind Belgium's 1.000 and Italy's 0.492. And **Italy's *scala mobile* years are not in the sample at all**: the Italian panel begins 1985Q4, after the *decreto di San Valentino*, so the episode that dominates the narrative contributes nothing to the estimates. The German sample excludes the pre-reunification period and the French sample begins after the 1983 *désindexation*, which is why French in-sample $\lambda$ varies by less than four hundredths across forty years.

### Sources and series choices

Prices are CPI or HICP headline, with core and the energy and food components alongside: FRED for the US (CPIAUCSL, CPILFESL, CPIENGSL, CPIUFDSL), ONS for the UK (RPI CDKO spliced forward onto CPI D7BT), Eurostat `prc_hicp_midx` for the euro-area countries, back-extended with the OECD's legacy quarterly series on FRED.

Wages are the mix-controlled series wherever one exists. For the US, the Employment Cost Index (wages and salaries), which FRED carries only from 2001, extended backwards with average hourly earnings of production and non-supervisory workers (1964–) and then nonfarm business compensation per hour. The splice is on growth rates, with the modern series authoritative for the level and at least four overlapping observations required so the rescaling ratio is an average rather than one possibly-revised point. For the UK, AWE regular pay (2000–) on the OECD hourly earnings index (1963–). For the euro-area countries, compensation per employee from the quarterly national accounts (`namq_10_a10` D1 over `namq_10_a10_e` EMP_DC), falling back to the labour cost index (`lc_lci_r2_q`, D11).

All series are pulled keylessly, with one substantive consequence: Destatis's *Tarifverdienstindex* is the German negotiated-wage analogue and the only series separating the *Inflationsausgleichsprämie* from base pay, but Genesis-Online serves it only behind a session API, so German measured wage growth in 2023–24 **includes** the tax-free bonus.

Labour-market tightness is the unemployment gap: a slow-moving reference rate minus the actual rate, using the CBO's NAIRU for the US and a five-year *trailing* moving average elsewhere, so no future information enters. The vacancy-to-unemployment ratio is Bernanke and Blanchard's preferred measure and clearly better over 2021–23, but exists only from 2001 for the US and UK; making it the default would cut the UK sample to 2001 and throw away the threshold episode. It is offered as an alternative rather than imposed.

### Four notable constructions

**The employment-weighted effective US minimum wage.** The federal floor has been \$7.25 since July 2009, so a series using it alone says the American wage floor has been frozen for seventeen years. That is false for most American workers: the binding minimum is the higher of the federal and state rate, and by 2026 roughly three-fifths of US employment is in a state with a higher one. We compute

$$MW_{t} \;=\; \sum_{s} \frac{E_{s,t}}{E_{t}} \, \max\bigl(MW^{\text{fed}}_{t},\, MW^{\text{state}}_{s,t}\bigr)$$

over the fifty states and DC, with state minima from FRED's `STTMINWG<ST>` and state employment from `<ST>NA`. States whose series are unavailable fall back to the federal rate, biasing the index *down*, never up. Without this the US minimum-wage channel in Eq. (W3) would be mechanically frozen after 2009.

**Year-on-year rather than annualised quarterly growth.** Bernanke and Blanchard can use annualised quarterly growth because their wage measure is the ECI, a fixed-weight index built for it. Outside the United States there is no ECI, and the available series — compensation per employee, OECD hourly earnings, average weekly earnings — carry enough quarter-to-quarter noise that their annualised quarterly growth is close to white; estimated on those, the wage equation returns a *negative* sum of own-lag coefficients, the signature of differencing noise rather than wage dynamics. Year-on-year growth is what the ECB wage tracker, the national negotiated-wage indicators and the statistical releases publish, and it is the natural unit for a catch-up term. The cost is overlapping observations and serially correlated residuals, so reported standard errors understate uncertainty; this is why the paper leans on coefficient sums and sign tests, and why the $t$-statistics below are upper bounds on the evidence. Annualised quarterly variants are retained so the choice can be inspected.

**The transfer-share impulse.** $h_{t} = 100(T_{t}/Y_{t} - T_{t-4}/Y_{t-4})$, with $T$ household social benefits in cash (Eurostat `nasq_10_nf_tr` D.62, ONS RVFJ, BEA A063RC1) and $Y$ gross household disposable income. A difference of ratios rather than a deflated flow, because the seven national accounts are published in six currencies, three base years and — for the UK, which left the Eurostat sector-account collection after 2019 — a different vintage discipline. A share is unit-free, so a units error in one source cannot silently rescale its coefficient, and $\varphi_e$ reads directly as points of household income handed out per point of excess inflation.

**Cyclical adjustment of transfers.** Total transfers are dominated by automatic stabilisers: unemployment insurance rises in recessions, when inflation is falling, so entered raw $h$ carries a spurious negative sign into the price equation. We project $h$ on the contemporaneous and four lagged changes in the unemployment rate and keep the residual — the part of the impulse policy chose rather than the cycle delivered. It is that residual, not the raw impulse, that enters Eq. (W5); an earlier vintage of the Python implementation used the raw series while the browser twin used the residual, so the two disagreed on $M$ for every country until the discrepancy was found. They now agree.

### The price/income distinction and the CPI wedge

Every scheme in the 2021–26 database is classified as `income`, `price` or `wage`, following the Eurostat (2022) criteria and the ONS classification statements. An `income` measure is a cash payment or voucher unrelated to the quantity consumed: it does not enter the HICP, it supports demand, and it enters the model through $h_t$. A `price` measure is a cap, a tariff freeze, an excise cut or a subsidised fare: it lowers measured inflation while in force, raises it on expiry, and adds nothing to nominal household income. A `wage` measure is paid through the payslip — Germany's *Inflationsausgleichsprämie* and France's *prime de partage de la valeur* are the cases that forced this third category to exist: they are in measured wages but not in the permanent wage base.

The price measures are then summarised as a wedge, in percentage points of year-on-year inflation:

| Country | Period | Wedge (pp) | Source |
|:----------|:---------|------------:|:--------------------------------------------|
| FR | 2022 | −2.6 | Banque de France: *bouclier tarifaire* and *remise carburant* |
| FR | 2023 | +0.4 | Banque de France |
| FR | 2024 | +1.0 | Banque de France |
| FR | 2025 | +0.8 | Banque de France |
| DE | 2022Q2 | −0.3 | Destatis: *Tankrabatt* and 9-Euro-Ticket from June |
| DE | 2022Q3 | −1.0 | Destatis: the two measures together |
| DE | 2022Q4 | −0.2 | measures expired 31 Aug; EEG-Umlage abolition persists |
| DE | 2023 | −0.8 | Jannsen and Sonnenberg: the electricity and gas price brakes |
| DE | 2024 | +0.6 | unwind of the price brakes |
| UK | 2022Q4 | −1.2 | pipeline assumption, anchored on the OBR's −2.5pp at the CPI peak |
| UK | 2023 | −2.0 | pipeline assumption, same anchor |
| UK | 2024 | +1.4 | pipeline assumption: unwind as the EPG ended in March 2024 |
| US | 2022 | −0.1 | state fuel-tax holidays only |
| US | 2023 | +0.1 | unwind |

The French and German rows are published estimates. The **UK rows are not**: the literature supplies only the OBR's statement that the Energy Price Guarantee cut the peak CPI inflation rate by 2.5 percentage points, and the quarterly and annual profile in the table is the pipeline's own interpolation around that anchor. The US rows are likewise assumptions, though of a size that cannot matter. Readers should treat the UK subsidy-neutral figures reported later as illustrative in a way the French ones are not.

The French profile is the clearest demonstration in the European literature that price measures shift inflation through time rather than removing it: a cumulative effect of about −0.4pp across four years on a scheme costing roughly 1.1% of GDP per year.

### Benefit uprating, implemented from statute

The `benefit` component of the Effective Wage Index is built from each country's uprating rule applied to observed data, not from a spending aggregate, since a spending aggregate moves with caseloads while the rule sets the entitlement of a representative recipient. The four rules are: Social Security Act s.215(i) for US OASDI (the increase in the third-quarter average CPI-W over the highest previous third-quarter average, floored at zero); SSAA 1992 s.150 for UK working-age benefits (September CPI, applied the following April) with the triple lock for the State Pension (the highest of September CPI, the May–July average of total-pay earnings growth, and 2.5%); CSS art. L161-25 for French pensions (the average of the twelve most recent monthly CPI-excluding-tobacco indices over the same average a year earlier, applied 1 January and floored at zero); and the *Rentenanpassungsformel* in its post-2024 form, where the 48% *Niveauschutzklausel* binds and the adjustment follows gross wage growth with the dampening factors suspended.

These are a genuine out-of-sample test of the data plumbing, since the US COLA is a deterministic function of CPI-W and any error in the price series shows up immediately. The implemented rules are checked against published decisions — 51 US COLA announcements from 1975, UK working-age and State Pension upratings from 2022, French pension revalorisations from 2022, German *Rentenanpassungen* from 2022 — at a tolerance of 0.35pp rather than 0.1pp, because three of the four are applied to a slightly different index from the statutory one, as the limitations set out.

## Results

### The partially pooled wage equation

Eq. (W4$'$), seven countries, country fixed effects, country-specific dynamics, common catch-up block, homogeneity imposed once per country. $n = 1177$, $k = 99$, $R^{2} = 0.868$.

| Block | Sum | $t$ by lag (1, 2, 3, 4) |
|---|---:|---|
| catch-up level (common) | −0.0599 | −5.14, 0.08, −2.08, 5.02 |
| catch-up $\times\ \lambda$ (common) | **+0.1096** | −0.70, −2.38, 1.28, 2.87 |

**The interaction shrinks by two-thirds when the dynamics are freed.** The fully pooled specification returned $\sum_k \tilde{d}_k = +0.3393$; with country-specific persistence, trend weight and slack response it is **+0.1096**. The catch-up level moves less, from −0.0881 to −0.0599. Two-thirds of what the earlier specification attributed to indexation was pooled-dynamics misspecification: a common persistence that fitted no country well, with the residual difference loading onto the one block that varied systematically across countries. We state this plainly because it is the most important thing in this revision, and because a reader who discovers it unaided has no reason to trust anything else in the paper.

The lag pattern also changes, and not for the better. The interaction's $t$-statistics are −0.70, −2.38, +1.28 and +2.87: the fourth lag is still significant and positive, which is where an annual clause or a January uprating bites, but the second is significant and negative, as in the pooled version. The block is not cleanly signed, and a positive sum built from a $+2.87$ and a $-2.38$ is weaker evidence than a positive sum built from four positive coefficients. Either the pattern is a genuine annual rhythm, with the intervening quarters carrying the offsetting arithmetic of a four-quarter growth rate, or the lag polynomial is poorly determined and only the sum is interpretable; we cannot separate the two. Both readings support using the sum, which is what $\Lambda$ is built from; neither supports precision claims about individual lags. And with classical errors on overlapping observations, even the $2.87$ overstates the evidence.

The comparison with Bernanke and Blanchard's published coefficient sums is run on the restricted, *fully pooled*, non-interacted specification, because that is the object of their Table 1, and it is worth reporting without flattery. On the full sample that split is **0.598 / 0.402**, carried by the validation suite as its own check (`bernanke_blanchard/full_sample_split`) so it cannot go stale. On **their** window, 1990Q1–2019Q4, it is **0.639 / 0.361** against their 0.460 / 0.540 — a 0.179 gap, clearing the module's 0.20 tolerance by 0.02. We are not going to call that close. What it establishes is narrower: that the estimator puts substantial weight on the expectations term rather than loading everything onto persistence. That is why the check runs on a panel at all — on one country's year-on-year series $\pi^{*}$ is close to collinear with four lags of wage growth, and the United States alone splits 0.97 / 0.03.

The country-specific dynamics are in the table below. What the freed specification buys, apart from credibility, is the persistence column: the United States at 0.967 is close to a unit root in the four-quarter growth rate, Italy at 0.222 is not, and France and Belgium put most of their weight on the anchor (0.507 and 0.642 respectively) rather than on their own past. The tightness sums are positive in five of seven, negative and near zero in the United States (−0.006) and Belgium (−0.039); we do not read anything into the two negatives beyond the fact that an unemployment gap is a weak slack proxy in a country with a compressed unemployment cycle.

### The catch-up schedule $\Lambda(\lambda)$

There is no longer a single $\Lambda(\lambda)$ line. Because persistence is country-specific and the catch-up coefficients are common, the same impulse propagates differently in each country and Eq. (W6) delivers seven lines, each still exactly linear in $\lambda$ and so summarised by its intercept and slope:

| country | own-lag sum | $\pi^{*}$ sum | slack sum | $\Lambda(0)$ | $\Lambda(1)$ | $\partial\Lambda/\partial\lambda$ |
|---|---:|---:|---:|---:|---:|---:|
| US | 0.967 | 0.033 | −0.006 | −0.722 | −0.545 | **+0.177** |
| UK | 0.675 | 0.325 | +0.169 | −0.183 | +0.181 | **+0.364** |
| FR | 0.493 | 0.507 | +0.053 | −0.110 | +0.139 | **+0.249** |
| DE | 0.673 | 0.327 | +0.069 | −0.189 | +0.115 | **+0.304** |
| BE | 0.358 | 0.642 | −0.039 | −0.091 | +0.084 | **+0.175** |
| IT | 0.222 | 0.778 | +0.262 | −0.073 | +0.029 | **+0.102** |
| ES | 0.335 | 0.665 | +0.151 | −0.092 | +0.067 | **+0.159** |

**The slope is the paper's result, and it is positive in all seven countries, from +0.102 to +0.364.** Moving a country from no indexation to full indexation raises the three-year recovery of a real-wage loss by that much per point of gap. That sign survived the specification change which destroyed two-thirds of the magnitude, and surviving is the stronger claim: an effect that vanishes when the dynamics are freed was never an effect, and one that shrinks but keeps its sign in every country is evidence about direction if not about size.

**The *level* of $\Lambda$ is not comparable across countries.** It is dominated by persistence — the United States has $\Lambda(0) = -0.722$ because its own-lag sum is 0.967, so any impulse is amplified over three years, while Italy has −0.073 on a sum of 0.222. That difference is about wage dynamics, not indexation, and it is an expected consequence of estimating on overlapping four-quarter growth rates. Report the derivative; caveat the level.

Two readings of the intercepts are nevertheless defensible within a country. Every $\Lambda(0)$ is negative: without indexation a real-wage loss is not recovered within three years, and the point estimate everywhere is that wage growth is marginally slower after one. And at $\lambda = 1$ six of the seven turn positive, the United States excepted at −0.545, because its persistence is high enough that even full indexation would not deliver recovery within three years on these estimates. The implied zero crossings, $-\Lambda(0)/(\partial\Lambda/\partial\lambda)$, lie between 0.44 (France) and 0.72 (Italy) for the six, with the United States outside $[0,1]$ entirely. At their *actual* $\lambda$ today, $\Lambda$ is negative in six of seven countries and positive only in Belgium, at +0.084.

$\Lambda(1)$ carries the same warning as before, unchanged by the new specification: **it is an extrapolation.** Inside the estimation sample $\lambda \ge 0.9$ comes from Belgium alone — 101 quarters at a constant 1.000 — and no other country supplies an observation above 0.5. Because Belgian $\lambda$ never moves, it is absorbed by the Belgian fixed effect except through the interaction, so the top of every one of the seven lines is anchored by one cross-sectional cell. It remains the weakest link in the paper.

### Mean-group robustness

The fully heterogeneous alternative is the Pesaran–Smith mean-group estimator: fit each country separately, then average. It is consistent under exactly the slope heterogeneity the Chow test says we have, so it is the right robustness check even though it cannot be the headline. Its standard error is the cross-country standard deviation over $\sqrt{7}$, which measures disagreement between countries rather than sampling error, and with $N = 7$ it is indicative at best.

Block sums of the country-by-country averages:

| block | sum of mean-group coefficients |
|:-----------------------|------------------------------:|
| own lags | +0.494 |
| trend inflation | +0.506 |
| tightness | +0.076 |
| catch-up level | −0.043 |

And the catch-up block lag by lag, with the spread across the seven countries:

| coefficient | mean group | se | min | max |
|:--------------|-------------:|--------:|---------:|---------:|
| cu_l1 | −0.161 | 0.045 | −0.371 | −0.003 |
| cu_l2 | −0.111 | 0.053 | −0.373 | +0.053 |
| cu_l3 | −0.011 | 0.012 | −0.050 | +0.035 |
| cu_l4 | +0.239 | 0.062 | +0.031 | +0.456 |

The averages are reassuring where they can be: the persistence/anchor split is 0.49 / 0.51, tightness is positive, and the catch-up level is negative and close to the partially pooled −0.0599. The spread behind that average is the informative part. The fourth-lag-positive, first-lag-negative pattern is not an artefact of pooling — every one of the seven first lags is negative and every one of the seven fourth lags positive — and the spreads are wide relative to the means, which is the Chow test's message again.

The interaction is absent by construction, and that absence is the argument for the headline specification. Within a country $\lambda$ is near-constant, so a country-level interaction is identified off almost nothing: estimated freely, the per-country catch-up coefficients range from −0.371 to −0.003 on the first lag alone, and averaging seven noisy numbers does not manufacture identification the within-country variation does not contain. That is what "not identified within a country" looks like, and it is why the interaction stays common while everything the test rejects pooling on is freed.

### Wage-to-price pass-through and the Spiral Gain

| country | $M$ (3yr) | $\lambda$ 1975 | $\lambda$ now | $G$ 1975 | $G$ now | $\partial G/\partial\lambda$ |
|---|---:|---:|---:|---:|---:|---:|
| US | 0.968 | 0.117 | 0.019 | −0.678 | −0.695 | +0.171 |
| UK | 1.386 | 0.119 | 0.102 | −0.193 | −0.202 | +0.505 |
| FR | 0.737 | 0.371 | 0.236 | −0.013 | −0.038 | +0.184 |
| DE | 0.760 | 0.107 | 0.069 | −0.119 | −0.128 | +0.231 |
| BE | −0.083 | 1.000 | 1.000 | −0.007 | −0.007 | −0.015 |
| IT | 0.971 | 1.000 | 0.320 | +0.028 | −0.039 | +0.099 |
| ES | 0.689 | 0.000 | 0.150 | −0.063 | −0.047 | +0.110 |

The last column is $M \times \partial\Lambda/\partial\lambda$, computed from the two preceding tables rather than estimated separately; everything else comes from the model.

$M$ is close to unity in the United States (0.968), Italy (0.971) and above it in the United Kingdom (1.386), lower in France (0.737), Germany (0.760) and Spain (0.689), and **effectively zero in Belgium at −0.083**. The UK value above one is not more than full pass-through — homogeneity pins the long run at exactly one — but front-loading: overshooting at three years and converging back. These figures changed from an earlier vintage because the price equation was reading the raw transfer impulse where the documentation and the browser twin both specified the cyclically adjusted one; the Python and JavaScript implementations now agree.

**$G$ is negative in all seven countries today.** No economy in this panel has a self-reinforcing loop, and none is remotely near the threshold of one. Only a single cell in the whole table is positive: Italy in 1975, at **+0.028**, under the *punto unico* with $\lambda$ at the clip. That is a far smaller number than the earlier, fully pooled specification produced, and the reason is the same two-thirds shrinkage — the 1975 Italian cell was the single largest beneficiary of the pooled-dynamics misspecification, because it combined the maximum $\lambda$ with a persistence borrowed from countries that do not resemble Italy.

Since $G = \Lambda \times M$ and the *level* of $\Lambda$ is persistence-dominated, the level of $G$ inherits the same warning: the cross-country ordering of $G$ is not interpretable, and the United States' −0.695 says more about an own-lag sum of 0.967 than about American wage-setting institutions. What is robust is the *sign* — negative everywhere today — and the *derivative*, $\partial G/\partial\lambda = M \times \partial\Lambda/\partial\lambda$, which is positive in six of seven countries, ranging from +0.099 in Italy to +0.505 in the United Kingdom.

Belgium is the seventh, and its sign is the paper's sharpest single result. Its $\partial G/\partial\lambda$ is **−0.015**: because Belgian wage-to-price pass-through is effectively zero, more indexation in Belgium does not raise its spiral gain at all. The first leg of the loop is complete and the second is missing, so the product is nothing. That is not a quirk of our estimates; it is what the National Bank of Belgium finds by other means.

### Belgium: high $\lambda$, low $M$

Belgium is where the product structure earns its keep, and where the estimates are thinnest. It has the highest possible $\lambda$ — one, throughout, by construction and by fact — and a wage-to-price pass-through of **−0.083**, indistinguishable from zero and the lowest in the panel by a wide margin. It is also the only country whose $\Lambda$ is positive today, at +0.084: a real-wage loss there *is* recovered within three years, and it is the only economy in the sample of which that is true. The two facts together are the whole argument. The first leg of the loop is complete and the second is missing, so $G$ is −0.007 and $\partial G/\partial\lambda$ is −0.015: more indexation in Belgium buys more wage recovery and no more inflation.

That is a finding we reproduce rather than invent. Bernanke and Blanchard (2024) report Belgian cumulative pandemic-era wage inflation of 17.8% against a euro-area 7.5%, with cumulative price inflation of 15.6% against 15.8%: indexation raised Belgian wages far more without raising prices more, implying firms absorbed it through margin compression. Jonckheere and Zimmer (2024) reach the same conclusion from the National Bank's own models — compensation per employee grew 7.3% in 2022 and 7.7% in 2023 against euro-area rates of 4.5% and 5.2%, prices-to-wages transmission is "much stronger" in Belgium, and yet "wages barely explain core inflation in Belgium, whereas they seem to matter in the euro area" — and judge the risk of a rampant spiral contained. Our $M = -0.083$ is a quantitative version of their sentence, arrived at independently. Geis, Wong and Vernon (2023) document the margin through which it operates: the 1996 Wage Law caps real wage growth by reference to the three neighbours, so because indexation exhausted the margin no real wage growth was permitted for 2022–24, with the Central Economic Council estimating a 2.9pp wage gap at end-2022 projected to reach 5.7% by end-2024.

The policy content cuts against the intuition the 1970s literature left behind. **An indexation regime is not automatically an inflation regime.** Whether it becomes one depends on the second factor in the product — on whether firms can and do pass labour costs into prices, which depends on competition, openness, margins and the credibility of the monetary anchor. Belgium is a small open economy with a statutory wage norm tied to its three largest trading partners; its firms cannot pass a national wage shock into prices without losing market share, so they compress margins instead. The same $\lambda$ in a large, closed, high-margin economy would produce a materially different $G$. The caveat is the one that will not go away: everything here that depends on $\lambda = 1$ is anchored by Belgium itself, so the row is internally consistent rather than independently corroborated.

### Real wage paths

Cumulative percentage change in the real wage. The first five columns are measured against 2019Q4; the last, headed *2022 vs 2021*, is measured against 2021Q4 instead, which is the base the ECB uses:

| country | 2021Q4 | 2022Q4 | 2023Q4 | 2024Q4 | trough | 2022 vs 2021 |
|:----------|---------:|---------:|---------:|---------:|---------:|-------------:|
| US | −0.17 | −2.01 | −0.97 | −0.01 | −2.12 | −1.84 |
| UK | +3.91 | −0.33 | +1.19 | +4.65 | −0.33 | −4.24 |
| FR | −0.51 | −2.45 | −2.97 | −2.58 | −4.22 | −1.94 |
| DE | +0.65 | −4.82 | −1.45 | +0.71 | −4.82 | −5.47 |
| BE | −1.97 | −4.94 | +2.10 | −0.17 | −4.94 | −2.97 |
| IT | +1.92 | −7.28 | −4.96 | −2.66 | −7.28 | −9.20 |
| ES | +1.16 | −0.41 | +0.70 | +3.11 | −2.63 | −1.57 |

Four things stand out. First, the losses were large and concentrated in 2022: troughs against 2019Q4 of −7.3% in Italy, −4.9% in Belgium and −4.8% in Germany. The ECB's aggregate estimate is about −5% for HICP-deflated compensation per employee from 2021Q4 to 2022Q4 (Bates, Bodnár, Botelho and Rousseau 2025), a different base period, so the comparison belongs in the last column: on a 2021Q4 base our euro-area countries record −9.20% (Italy), −5.47% (Germany), −2.97% (Belgium), −1.94% (France) and −1.57% (Spain). They bracket −5% widely, Germany closest and Italy more than twice as deep; we claim only that the aggregate lies inside the range our series span.

Second, Belgium has the *fastest recovery*, though not the deepest trough — Italy's −7.28% is deeper, and on a 2021Q4 base Germany's −5.47% is too. What is distinctive is the round trip: from −4.94% at end-2022 to +2.10% a year later, a swing of seven points in four quarters that no other country approaches. That is the indexation mechanism working as designed — a lag of a few quarters between the price shock and the pay rise, then full restoration. The NBB dates the recovery of Belgian purchasing power to 2023Q1; our path has it completing during 2023, the difference attributable to our use of headline HICP rather than the health index and compensation per employee rather than the negotiated-wage measure.

Third, two countries have still not recovered by 2024Q4: Italy at −2.66% and France at −2.58% below their 2019 levels, Italy the worse. They arrive there differently — Italy fell furthest (−7.28%) and has clawed back two-thirds, France had a shallower trough (−4.22%) and has clawed back very little. The French combination of a high $\lambda$ and a low $M$ with an absent recovery is not what a simple indexation story predicts; we read it as the joint product of a shielded price index — the *bouclier* held measured inflation down, propping up the measured real wage in 2022 and dragging it down afterwards as the shield unwound — and weak nominal wage growth.

Fourth, the two Anglophone economies are not where the continental ones are: the UK real wage never falls more than a third of a point below its 2019 level and is 4.65% above by end-2024, and the US troughs at −2.1% and returns to flat. The UK series is AWE total-economy regular pay, which is not mix-adjusted, and UK composition shifts over 2020–22 were unusually large, so the UK level should be treated with more caution than the others.

## The Effective Wage Index

### What it measures

The Effective Wage Index answers a question no wage series answers: what happened to the *income* of a household, as opposed to the *price of labour*. For a household in the bottom quartile, market earnings are less than half of gross income everywhere in the sample — 0.42 in the US, 0.34 in the UK, 0.30 in France, 0.33 in Germany — and indexed benefits are between 0.39 and 0.52. A real-wage series is a statement about a minority of that household's income; the majority of it moves by statute.

The index combines four level indices, each 100 in 2019Q4, under Eq. (W10): the market wage, the statutory floor, the statutory benefit entitlement built from the uprating rule, and the handout term, which is one plus the annualised scheme amount as a share of household disposable income and therefore sits at exactly 100 in every quarter with no scheme in payment. A one-off payment adds to income growth in the year it is made and subtracts from it the year after — exactly what a one-off does, and exactly what an aggregate wage index cannot show. Income-composition shares come from CBO for the US (quintile shares rebased to quartiles), ONS for the UK, INSEE and DREES for France, and Destatis EVS and DIW SOEP for Germany, all fixed at 2019 values.

### Results

Real Effective Wage Index, 2019Q4 = 100, for the bottom quartile (`q1`) and all households, with the market real wage and the subsidy-neutral variant alongside:

| country | group | 2021Q4 | 2022Q4 | 2023Q4 | 2024Q4 | subsidy-neutral 2022Q4 | market real wage 2022Q4 |
|:--------|:------|------:|------:|------:|------:|----------------------:|----------------------:|
| US | q1 | 96.7 | 94.7 | 99.2 | 99.8 | 94.6 | 98.0 |
| US | all | 97.8 | 95.3 | 99.1 | 99.8 | 95.2 | 98.0 |
| UK | q1 | 101.2 | 99.6 | 107.0 | 113.5 | 99.3 | 99.7 |
| UK | all | 101.4 | 100.2 | 106.7 | 112.8 | 99.9 | 99.7 |
| FR | q1 | 95.5 | 94.0 | 94.8 | 96.2 | 91.6 | 97.6 |
| FR | all | 95.7 | 94.2 | 94.9 | 96.3 | 91.7 | 97.6 |
| DE | q1 | 98.2 | 94.0 | 96.5 | 99.5 | 93.6 | 95.3 |
| DE | all | 98.4 | 94.4 | 96.6 | 99.5 | 94.0 | 95.3 |

**The distributional finding.** In all four countries and at every date, the bottom quartile's measured real income is within one index point of the all-household figure. At end-2022 it is 0.6 points below in the United States (94.7 against 95.3), 0.6 below in the United Kingdom (99.6 against 100.2), 0.2 below in France (94.0 against 94.2) and 0.4 below in Germany (94.0 against 94.4). By end-2024 the bottom quartile is *ahead* of the average only in the United Kingdom (113.5 against 112.8); it is level in the United States and Germany and a tenth of a point behind in France. The finding is convergence, not reversal.

This is not what the income shares would suggest. The bottom quartile has less than half the wage exposure of the average household and roughly twice the benefit exposure; that the two groups end up together means the sources moved together, because statutory floors and indexed benefits roughly tracked prices while market wages did not. The United Kingdom is clearest: working-age benefits rose 10.1% in April 2023 on the September 2022 CPI, the State Pension rose 10.1% and then 8.5% under the triple lock, and the National Living Wage reached two-thirds of median earnings by April 2024. The UK bottom quartile at 113.5 is a statutory result, not a labour-market one.

Two qualifications cut the other way. The index measures gross income, not purchasing power net of the floor's own price effects: if 75–100% of a minimum-wage increase is passed to consumers (Harasztosi and Lindner 2019; Ashenfelter and Jurajda 2022), the floor is partly a value-added tax on the households it pays, and a regressive one (MaCurdy 2015). Our deflator is the aggregate CPI, which contains that pass-through only insofar as it is economy-wide; a group-specific deflator weighted toward food and limited-service categories would shrink the bottom quartile's measured gain, so the figures are an upper bound on its relative performance. And the 2022 squeeze was *not* smaller for the bottom quartile than for market earnings: in all four countries the q1 EWI at end-2022 sits **below** the market real wage — 94.7 against 98.0 in the US, 99.6 against 99.7 in the UK, 94.0 against 97.6 in France, 94.0 against 95.3 in Germany. The reason is timing, not generosity. Benefit upratings and floor revisions are annual, backward-looking and applied on a fixed date, so in the year of a shock they deliver last year's inflation while the shock delivers this year's; the components dominating the bottom quartile's income lag precisely when lagging hurts. The catch-up arrives afterwards and is large — US 94.7 to 99.8, Germany 94.0 to 99.5, the UK 99.6 to 113.5 by end-2024. Statutory indexation lags are distributionally regressive in the year of the shock and restorative over the following two, which is the same lag structure the wage equation finds in the bargained sector, arriving through a different institution.

### The subsidy-neutral variant and the size of the wedge

The subsidy-neutral column deflates by the reconstructed index $\tilde{P}$ that removes the price-based support measures. The gaps at end-2022, for the bottom quartile, are: France 2.4 index points (94.0 against 91.6), Germany 0.4, the United Kingdom 0.3, the United States 0.1.

France dominates because the *bouclier tarifaire* was the largest price intervention relative to the index it acted on: about −2.6pp of HICP inflation in 2022 on the Banque de France's estimate, against −0.8pp for Germany's price brakes in 2023 and, on the pipeline's own assumption rather than a published estimate, around −1.2pp for the UK's Energy Price Guarantee in 2022Q4. Read the French column in the right direction: **the recorded 6.0-point real income loss for the French bottom quartile at end-2022 understates by 2.4 points what the same households would have recorded had the same money been delivered as income rather than as a lower price.** The subsidy-neutral loss is 8.4 points, not 6.0. Had France transferred the €42.7bn it spent on the tariff shields and the fuel rebate — a sum over the scheme database, not a published total — instead of capping prices, the measured French real EWI at end-2022 would have been about 91.6 rather than 94.0, measured French inflation in 2022 about 2.6 points higher, and the reversal would have arrived in 2023–25 exactly as it did, except that the cash would have been in household budgets in 2022 and available to spend — precisely the difference the price equation's transfer term exists to price.

The German and UK wedges are smaller because those countries used a more even mix. On the same scheme database Germany delivered €17.3bn of pure income support (the three *Energiepreispauschale* tranches) alongside €30.6bn in the two price brakes, with the *Inflationsausgleichsprämie* on top as a payroll measure invisible to both. The UK's £12bn Energy Bills Support Scheme and £20bn of Cost of Living Payments are income; its £23–24.8bn Energy Price Guarantee is price. The US, with no federal price intervention, has a wedge of a tenth of a point.

## The fiscal loop

### The reaction function and the transfer term

The loop has two return paths from prices to incomes. The first runs through the wage bargain and is governed by $\lambda$. The second runs through the budget: a price shock produces political pressure, the pressure produces a transfer, the transfer produces demand, the demand produces prices. Eq. (W9) specifies the first stage and Eq. (W5)'s $h$ term the last.

The transfer term is deliberately narrow. It carries only income-based measures, because a price-based measure adds no nominal household income; only the *discretionary* part of the impulse, because the cyclical part is negatively correlated with inflation and would enter with a spurious sign; and it is expressed as a change in the share of household disposable income, so its coefficient reads directly.

We report no estimated coefficients for Eq. (W9). The results assembled for this paper do not contain them, and we will not report numbers we have not computed. What follows is therefore a characterisation of the design and an account of what is not identified.

### What the simulator does

Eq. (W12) propagates a relative energy price shock through the estimated price equation, the estimated wage equation, the expectations filter, a one-sided handout rule and a reduced-form monetary rule, with $\lambda$, the anchoring gain $q$, the fiscal response $\varphi_e$, the marginal propensity to consume, the sacrifice dial $\tau$ and the shock's size and duration all exposed.

The qualitative structure is where the policy content lies, and it survives the absence of estimated fiscal coefficients. A government facing a supply shock has three instruments and they are not equivalent. It can do nothing, in which case $\lambda$ determines how much of the real income loss comes back as wages and $M$ how much of that returns as prices. It can cap prices, in which case measured inflation falls now and rises later, the catch-up term is mechanically suppressed while the cap is in force because the measured real wage does not fall as far, and the adjustment is deferred — the Banque de France profile of −2.6, +0.4, +1.0, +0.8 is what deferral looks like. Or it can transfer income, leaving measured inflation mechanically unaffected but raising demand, with the $h$ term converting some fraction into inflation with a lag.

How large that fraction is depends on where the money is spent and how steep the supply curve is where it lands, and this is where Orchard, Ramey and Wieland (2025) does real work. A transfer with a corrected micro MPC of about 0.3, concentrated in durables and meeting a steep short-run supply curve, produced a relative price spike of about 1.0% in motor vehicles and a consumption multiplier of about 0.06: the quantity response was small precisely because the price response was not. Applied to 2021–24, an untargeted energy handout paid into an economy whose binding constraint is the supply of energy and energy-intensive goods should show up disproportionately in prices — and the worst configuration is a handout paid alongside a cap on the same good, because the cap suppresses the signal that would ration demand while the transfer raises the demand to be rationed. That describes several packages in the database.

The two interventions also interact with $\lambda$ in opposite directions. A cap *substitutes* for indexation: holding the measured CPI down shrinks the real-wage gap and hence the catch-up claim, which is why a capped economy with high $\lambda$ can look quiescent while the cap holds and then experience the catch-up when it unwinds. A transfer does not substitute at all: it leaves the gap intact, so the wage claim still arrives, and adds demand on top. In an economy with $\lambda$ near one a transfer is therefore additive to the indexation response while a cap is partly a substitute for it — an argument for caps in highly indexed economies and transfers in weakly indexed ones, the opposite of the standard advice. We flag it as a hypothesis the model generates rather than a result, because the fiscal coefficients that would test it are the ones we lack. Against it stands the evidence that caps are expensive, badly targeted and internationally harmful: Europe spent roughly 4.4% of GDP against an IMF estimate that compensating the bottom 40% fully would have cost about 0.9% (Ari et al. 2022); 73% of household-directed funding was untargeted (Sgaravatti et al. 2023); only about 12% was explicitly targeted (Bańkowski et al. 2023); and Komatsu (2025) finds caps raised headline inflation in the *uncapped* members. And the monetary reaction is not a spectator: Glover and Mustre-del-Río (2021) show for the statutory wage floor what $\tau$ encodes generally, a doubling of the US federal minimum raising inflation about 2.5pp annualised under a fixed nominal rate but only about 1pp under the Taylor principle. Whether any instrument is inflationary is jointly determined with the central bank's response, and Eq. (W12) makes that an explicit dial.

### The populism channel, and why it is not identified

Eq. (W9) contains a coefficient $\varphi_P$ on a populist-executive indicator, and the honest report is that **it cannot be estimated in this sample**. The political table codes populist status from Funke, Schularick and Trebesch (2023). None of the four modelled countries had a populist executive under that coding over the estimation period, and the table carries no political rows for the three reference countries. The indicator is therefore identically zero at every observation used: $\varphi_P$ is not weakly identified or imprecisely estimated, it is not identified at all.

We regard this as a design finding. A fiscal reaction function with a populism term requires a sample containing populist executives, which means a longer historical panel or a wider cross-section — Latin America in the 1980s, central Europe after 2010, or the emerging-market fuel-subsidy universe. What the mechanism would look like is clear from the literature: Dornbusch and Edwards (1991) describe a regime that sets $\varphi_e$ high and $\varphi_P$ positive, suppresses the measured price signal through administered prices, and thereby prevents the relative price adjustment that would have ended the episode — so the loop runs for longer, not faster.

The cross-country evidence gives the shape of the design. Fails (2025) shows that across more than ninety democracies over 1990–2015 electoral proximity depresses fuel prices specifically in low-state-capacity democracies facing uncertain re-election, which maps onto our price/income distinction: states that can transfer, transfer; states that cannot, cap prices. That implies estimating the reaction function with an *interaction* between the political indicator and fiscal capacity, and with the price-based and income-based instruments as separate dependent variables. Amaglobeli, Gu, Hanedar, Hong and Thévenot (2023), covering 174 countries and some 750 announced measures in the first half of 2022, supply the reason such subsidies persist: social unrest over price increases for energy and basic goods. Hungary's *rezsicsökkentés* is the obvious European case of a durable administered-price regime under a government FST codes as populist, and Hungary recorded the EU's highest inflation in 2023; the IMF Selected Issues Paper on Hungarian inflation drivers could not be retrieved for this work, so we cite it as a lead requiring verification rather than as evidence.

The design for future work follows: extend the panel to economies with populist executives in the FST coding, code the price-based and income-based instruments separately, interact the political indicator with fiscal capacity, and estimate Eq. (W9) as a system. Until that is done the fiscal half of the Spiral Gain, $\Phi$ in Eq. (W8b), is a specified object with no estimate attached, and every result here is a $G = \Lambda \times M$ result with the fiscal route set to zero.

## Limitations

This section is not a formality, and the items are not of the same kind.

**The level of $\Lambda$ is persistence-dominated and not comparable across countries.** Because the partially pooled specification gives each country its own dynamics, the same common catch-up coefficients propagate through very different autoregressions, and the three-year gain inherits the difference: $\Lambda(0) = -0.722$ in the United States on an own-lag sum of 0.967, against −0.073 in Italy on a sum of 0.222. Those intercepts say almost nothing about indexation and almost everything about wage-growth persistence. Only the derivative $\partial\Lambda/\partial\lambda$ is comparable, and only it is reported as a cross-country statistic. The same warning passes to $G = \Lambda \times M$, whose cross-country ordering is not interpretable either.

**Near-unit-root persistence is a consequence of the year-on-year specification.** Four-quarter growth rates observed quarterly are highly autocorrelated by construction, so own-lag sums close to one are expected rather than surprising, and the US figure of 0.967 should be read that way. It is the price of the data constraint set out in the data section — outside the United States there is no mix-controlled quarterly wage index — and it is the mechanism by which the level of $\Lambda$ becomes uninformative. A specification in annualised quarterly growth would not have this problem and would have a different, worse one: a negative sum of own-lag coefficients, which is what differencing noise looks like.

**The two-thirds shrinkage is itself a caveat about everything upstream.** The interaction fell from +0.339 to +0.110 on a specification change. We have no way of knowing that the partially pooled specification is the last such change, and a reader should treat +0.110 as a number that has already proved sensitive to how the dynamics are handled rather than as a settled magnitude. The sign, which held in all seven countries across that change, is the claim we are willing to defend.

**$\Lambda(1)$ is an extrapolation from one country.** This is the most serious limitation. Inside the estimation sample, $\lambda \ge 0.9$ is contributed by Belgium alone — 101 quarters at a constant 1.000 — and no other country supplies an observation above 0.5. Belgium's constancy means the level is absorbed by its fixed effect, so the top of the schedule rests on one cross-sectional cell interacted with within-Belgium variation in the real-wage gap. Anything specific to Belgium that correlates with its real-wage gap — the 1996 Wage Law, its trade openness, its margin structure — is a confounder the fixed effect cannot absorb, because it enters through the same interaction. A second country with near-universal indexation would settle it; Luxembourg, Cyprus and Malta are the obvious candidates and are not in the panel.

**The narrative episodes are mostly outside the estimation sample.** Italy's *scala mobile* at the clip, the US COLA peak and the French *échelle mobile* are described from the database and displayed in the $\lambda$ table, but only the US episode is inside a sample: Italy and France both contribute from 1985Q4, after their reforms. The historical narrative and the econometrics rest on partly disjoint evidence, and the 1970s discussion should not be read as estimated.

**There is no published series to validate against.** Nobody publishes an indexation intensity, a spiral gain or an effective wage index. Validation is four weaker, independent checks — statutory uprating rules reproduced against announced decisions, similarity to Bernanke and Blanchard's coefficient sums, internal coherence, and institutional facts the coverage database must encode — and none is a ground-truth comparison.

**The Bernanke–Blanchard comparison is a similarity check, not a replication, and not a close one.** Their equation needs the ECI back to 1990 (keyed BLS API) and the Barnichon help-wanted index (a manual download); we have neither. On their own window the split is 0.639 / 0.361 against their 0.460 / 0.540, clearing the module's 0.20 tolerance by 0.02 and failing any tighter one. A check that passes by 0.02 establishes very little, and we do not lean on it.

**The standard errors are understated.** The left-hand side is a four-quarter growth rate observed quarterly, so consecutive observations share three quarters of data and residuals are serially correlated by construction; and the errors are classical rather than HAC, because the estimator must be reproducible exactly in a browser twin. The interaction's $t = 4.14$ is therefore an upper bound on the evidence, not a lower one, and no inference here should be read as significant at a conventional level.

**$\lambda$'s elasticities are calibrated, not estimated,** each at or below its source's central estimate. Since $\Lambda(\lambda)$ is linear in $\lambda$ and $\lambda$ linear in the elasticities, a proportional error in one is a proportional error in that channel's contribution. The `automatic` value of 0.90 (Card 1986) matters most for the 1970s; the `minwage` value of 0.35 matters most for the modern French and British results and rests on a contested spillover share — Autor, Manning and Smith (2016) cannot reject that measured spillovers are reporting artefacts, and if they are right the channel is materially smaller, French and British $\lambda$ fall toward the US and German range, and France drops further below the crossover. That is the calibration on which the modern cross-section is most fragile.

**Coverage shares are interpolated between documented dates,** which is an assumption about how contract expiry spreads an institutional change across the workforce; where the true path is a step (the UK in 1974) it is encoded as one. The US automatic channel after 1995 is an assumed decay, because the BLS programme that measured it was discontinued, and Spanish coverage before 2000 is undocumented and therefore recorded as zero.

**Several data substitutions are material.** The French uprating statute names the national CPI excluding tobacco and we apply the rule to the harmonised index; the German *Rentenanpassungsformel* carries dampening factors requiring counts no keyless source publishes quarterly; the UK triple lock references May–July total pay including bonuses. Belgian indexation runs off the health index and Italian benefit indexation off a forecast index, neither in the pipeline, so both are approximated as wage-linked. The uprating checks run at a 0.35pp tolerance for exactly these reasons.

**German measured wage growth includes the *Inflationsausgleichsprämie*.** Destatis publishes the *Tarifverdienstindex* including and excluding one-offs — precisely the split needed — but Genesis-Online serves it only behind a session API. German wage growth here is compensation per employee, which includes the bonus; with 86.3% coverage at an average of €2,680 the effect is not small, biasing measured German catch-up upward in 2023–24 and downward in 2025. This is an instance of exactly the measurement problem the paper is about.

**Unverified model inputs.** The income-composition shares are fixed at 2019 values, so compositional change is not captured; they are assembled from CBO, ONS, INSEE/DREES and Destatis/DIW sources without a single harmonised release behind them, and the US quartiles are a re-basing of published quintile shares. The same applies to the US union-density series multiplying the COLA share: the US automatic channel is a product of two series, so an error in either propagates one-for-one.

**Further specification caveats.** The pooled equation imposes common slopes across seven heterogeneous economies; relaxing them abandons identification of the interaction. $M$ is estimated once per country and held fixed, so all time variation in $G$ is institutional by construction, and the rolling-window variant is the appropriate robustness check. The Belgian *saut d'index* of 2015–16 is not encoded as a coverage reduction, so Belgian $\lambda$ is slightly overstated in those years. And the CPI wedges come from national estimates produced on different methodologies, so the cross-country comparison of wedges is looser than the within-country time profile.

Separately: we could not locate a peer-reviewed paper estimating the effect of the French 1983 *désindexation* on price–wage pass-through. The institutional facts are solid; the econometrics of what is arguably the cleanest indexation reform in a large advanced economy appear not to exist. That gap is itself an invitation.

## Conclusion

A wage–price spiral requires two things at once, and for most of the past forty years only one of them has been true. Prices must come back as wages, which requires an institution, and wages must go back out as prices, which requires pricing power. Writing the loop as a product rather than as a single reduced-form coefficient makes it possible to say which of the two moved.

What moved was the first. On the institutional database assembled here, indexation intensity between 1975 and today fell 83% in the United States and 68% in Italy, 36% in France and 35% in Germany, 15% in the United Kingdom, and not at all in Belgium. France is mid-pack in the rate of decline but first among the modelled countries in the level, because a minimum-wage formula survived the reform that abolished general indexation; Belgium never reformed at all. Catch-up turns on that intensity in the direction the institutions predict: $\partial\Lambda/\partial\lambda$ is positive in every one of the seven countries, from +0.102 to +0.364. The second factor did not move in the same way. Wage-to-price pass-through at three years remains close to one in the United States and Italy and above it in the United Kingdom, and it is a feature of market structure rather than of wage-setting institutions — which is why Belgium, with complete indexation and a pass-through of −0.083, has a Spiral Gain of −0.007 and a $\partial G/\partial\lambda$ that is *negative*. Today no country in the panel has a positive Spiral Gain at all.

We would not push the statistical evidence further than it goes, and one episode in the writing of this paper is the reason. Estimated with all seven countries pooled onto one coefficient vector, the indexation interaction was +0.339; freeing the country dynamics, which a Chow test says is required, cut it to +0.110. Two-thirds of the effect was misspecification. What that leaves is a sign rather than a magnitude: positive in all seven countries, on a block whose second lag is significantly negative and whose standard errors are classical and computed on overlapping observations, with the top of the $\lambda$ range supplied by one country. What the paper offers with more confidence is the accounting: an auditable database of who was indexed to what, a decomposition separating the two legs of the loop, and a measure of household income that includes the statutory floor, the indexed benefit and the one-off cheque as well as the wage.

That last measure carries the result we did not expect. Through 2022–24, measured real income for the bottom quartile tracked the all-household average to within a percentage point in every country we examined, and by end-2024 the British bottom quartile was ahead of its own average. This did not happen through the labour market. It happened because minimum wages and benefit upratings are indexation by another name — mechanical, statutory, applied to the households with the least wage exposure, and absent from every negotiated-wage indicator the modern literature uses to conclude that indexation has disappeared. Indexation did not disappear. It moved from the collective agreement to the statute book, and from the median worker to the bottom of the distribution.

The open question is the one we could not answer. When markets do not return an inflation shock to households, governments increasingly do: €758 billion of it in Europe in seventeen months, roughly half through prices and half through incomes, with 73% of the household-directed part untargeted. We have specified the reaction function governing that response and the term through which it feeds back into prices, and shown why the coefficient on political incentive cannot be estimated from a panel of seven advanced economies none of which had a populist executive. Extending the panel to economies where it did, coding the price-based and income-based instruments separately, and interacting the political variable with fiscal capacity is the natural next step, and it is where the interesting variation now lives.

## References

Aaronson, D. (2001). "Price Pass-Through and the Minimum Wage." *Review of Economics and Statistics* 83(1), 158–169. DOI: 10.1162/003465301750160126.

Aaronson, D., E. French and J. MacDonald (2008). "The Minimum Wage, Restaurant Prices, and Labor Market Structure." *Journal of Human Resources* 43(3), 688–720. DOI: 10.3368/jhr.43.3.688.

Afrouzi, H., A. Blanco, A. Drenik and E. Hurst (2024). "A Theory of How Workers Keep Up With Inflation." *NBER Working Paper* 33233. https://www.nber.org/system/files/working_papers/w33233/w33233.pdf

Aldama, P., H. Le Bihan and C. Le Gall (2024). "What caused the post-pandemic inflation? Replicating Bernanke and Blanchard (2023) on French data." *Banque de France Working Paper* 967. https://www.banque-france.fr/system/files/2024-10/WP967.pdf

Alvarez, J., J. C. Bluedorn, N.-J. H. Hansen, Y. Huang, E. Pugacheva and A. Sollaci (2024). "Wage–price spirals: what is the historical evidence?" *Economica* 91(364), 1291–1319. DOI: 10.1111/ecca.12543. Working paper: *IMF Working Paper* 2022/221, DOI: 10.5089/9798400224294.001.a001.

Amaglobeli, D., E. Hanedar, G. H. Hong and C. Thévenot (2022). "Fiscal Policy for Mitigating the Social Impact of High Energy and Food Prices." *IMF Note* 2022/001. https://www.imf.org/-/media/files/publications/imf-notes/2022/english/insea2022001.pdf

Amaglobeli, D., M. Gu, E. Hanedar, G. H. Hong and C. Thévenot (2023). "Policy Responses to High Energy and Food Prices." *IMF Working Paper* 23/74. https://www.imf.org/-/media/files/publications/wp/2023/english/wpiea2023074-print-pdf.pdf

Amores, A. F., M. Christl, P. De Agostini, S. De Poli and S. Maier (2023). "Limiting Prices or Transferring Money? An ex-ante assessment of alternative measures to cope with the hike in energy prices." *JRC Working Papers on Taxation and Structural Reforms* 11/2023. https://euromod-web.jrc.ec.europa.eu/research/publications/limiting-prices-or-transferring-money-ex-ante-assessment-alternative-measures

Ampudia, M., M. J. Lombardi and T. Renault (2024). "The wage-price pass-through across sectors: evidence from the euro area." *BIS Working Paper* 1192 (also ECB Working Paper 2948). https://www.bis.org/publ/work1192.pdf

Angelini, E., N. Bokan, K. Christoffel, M. Ciccarelli and S. Zimic (2019). "Introducing ECB-BASE: The blueprint of the new ECB semi-structural model for the euro area." *ECB Working Paper* 2315. https://www.ecb.europa.eu/pub/pdf/scpwps/ecb.wp2315~73e5b1c3cd.en.pdf

Ari, A., N. Arregui, S. Black, O. Celasun, D. Iakova, A. Mineshima, V. Mylonas, I. Parry, I. Teodoru and K. Zhunussova (2022). "Surging Energy Prices in Europe in the Aftermath of the War: How to Support the Vulnerable and Speed up the Transition away from Fossil Fuels." *IMF Working Paper* 22/152. https://www.imf.org/-/media/files/publications/wp/2022/english/wpiea2022152-print-pdf.pdf

Ashenfelter, O. and Š. Jurajda (2022). "Minimum Wages, Wages, and Price Pass-Through: The Case of McDonald’s Restaurants." *Journal of Labor Economics* 40(S1), S179–S201. DOI: 10.1086/718190.

Auclert, A., M. Rognlie and L. Straub (2024). "The Intertemporal Keynesian Cross." *Journal of Political Economy* 132(12), 4068–4121. DOI: 10.1086/732531. *(Cited for the mechanism only; magnitudes not extracted for this paper.)*

Autor, D. H., A. Manning and C. L. Smith (2016). "The Contribution of the Minimum Wage to US Wage Inequality over Three Decades: A Reassessment." *American Economic Journal: Applied Economics* 8(1), 58–99. DOI: 10.1257/app.20140073.

Ball, L. (1988). "Is Equilibrium Indexation Efficient?" *Quarterly Journal of Economics* 103(2), 299–311. DOI: 10.2307/1885114.

Bańkowski, K., O. Bouabdallah, C. Checherita-Westphal, M. Freier, P. Jacquinot and P. Muggenthaler-Gerathewohl (2023). "Fiscal policy and high inflation." *ECB Economic Bulletin* Issue 2/2023. https://www.ecb.europa.eu/press/economic-bulletin/articles/2023/html/ecb.ebart202302_01~2bd46eff8f.en.html

Barro, R. J. and F. Bianchi (2023). "Fiscal Influences on Inflation in OECD Countries, 2020–2023." *NBER Working Paper* 31838. https://www.nber.org/papers/w31838

Bates, C., K. Bodnár, P. Healy and M. Roca I Llevadot (2025). "Wage developments during and after the high inflation period." Article, *ECB Economic Bulletin* Issue 1/2025. https://www.ecb.europa.eu/press/economic-bulletin/articles/2025/html/ecb.ebart202501_02~05fb781826.en.html

Bates, C., K. Bodnár, V. Botelho and F. Rousseau (2025). "Real wage catch-up in the euro area." Box, *ECB Economic Bulletin* Issue 5/2025. https://www.ecb.europa.eu/press/economic-bulletin/focus/2025/html/ecb.ebbox202505_04~a71cdfe394.en.html

Battistini, N., H. Grapow, E. Hahn and M. Soudan (2022). "Wage share dynamics and second-round effects on inflation after energy price surges in the 1970s and today." Box, *ECB Economic Bulletin* Issue 5/2022. https://www.ecb.europa.eu/press/economic-bulletin/focus/2022/html/ecb.ebbox202205_02~e203142329.en.html

Bernanke, B. S. and O. J. Blanchard (2024). "An Analysis of Pandemic-Era Inflation in 11 Economies." *NBER Working Paper* 32532. DOI: 10.3386/w32532. https://www.nber.org/system/files/working_papers/w32532/w32532.pdf

Bernanke, B. S. and O. J. Blanchard (2025). "What Caused the US Pandemic-Era Inflation?" *American Economic Journal: Macroeconomics* 17(3), 1–35. DOI: 10.1257/mac.20230195. Working paper: *NBER Working Paper* 31417, DOI: 10.3386/w31417.

Bianchi, F. and L. Melosi (2022). "Inflation as a Fiscal Limit." Jackson Hole Economic Policy Symposium, Federal Reserve Bank of Kansas City. https://www.kansascityfed.org/Jackson%20Hole/documents/9037/JH_Paper_Bianchi.pdf

Bijnens, G., S. Karimov and J. Konings (2023). "Does Automatic Wage Indexation Destroy Jobs? A Machine Learning Approach." *De Economist* 171(1), 85–117. DOI: 10.1007/s10645-023-09418-y.

Bing, M., S. Holton, G. Koester and M. Roca I Llevadot (2024). "Tracking euro area wages in exceptional times." ECB Blog, 23 May 2024. https://www.ecb.europa.eu/press/blog/date/2024/html/ecbblog20240523~1964e193b7.en.html

Black, S., A. A. Liu, I. Parry and N. Vernon (2023). "IMF Fossil Fuel Subsidies Data: 2023 Update." *IMF Working Paper* 23/169. https://www.imf.org/-/media/Files/Publications/WP/2023/English/wpiea2023169-print-pdf.ashx

Blanchard, O. (1986). "The Wage Price Spiral." *Quarterly Journal of Economics* 101(3), 543–565. DOI: 10.2307/1885696.

Blanchard, O. and J. Galí (2007). "Real Wage Rigidities and the New Keynesian Model." *Journal of Money, Credit and Banking* 39(s1), 35–65. DOI: 10.1111/j.1538-4616.2007.00015.x.

Blanchard, O. and J. Galí (2010). "The Macroeconomic Effects of Oil Price Shocks: Why Are the 2000s So Different from the 1970s?" In J. Galí and M. Gertler (eds.), *International Dimensions of Monetary Policy*, NBER/University of Chicago Press, 373–421. DOI: 10.7208/chicago/9780226278872.003.0008.

BLS (1995). "Major Collective Bargaining Settlements in Private Industry, Fourth Quarter and Full Year 1994." News release, 31 January 1995. https://www.bls.gov/news.release/history/barg_013195.txt

Boissay, F., F. De Fiore, D. Igan, A. Pierres Tejada and D. Rees (2022). "Are major advanced economies on the verge of a wage-price spiral?" *BIS Bulletin* 53. https://www.bis.org/publ/bisbull53.pdf

Bordo, M., O. Bush and R. Thomas (2025). "'Muddling through or tunnelling through?' UK monetary and fiscal exceptionalism and the Great Inflation." *Bank of England Staff Working Paper* 1135. https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2025/muddling-through-or-tunnelling-through-uk-monetary-and-fiscal-exceptionalism-and-the-great-inflation.pdf

Bourgeois, A. and R. Lafrogne-Joussier (2022). "La flambée des prix de l'énergie : un effet sur l'inflation réduit de moitié par le « bouclier tarifaire »." *Insee Analyses* 75. https://www.insee.fr/fr/statistiques/6524161

Brayton, F. (2013). "A New FRB/US Price-Wage Sector." Federal Reserve Board methodological note, 30 August 2013, distributed with the FRB/US package. https://www.federalreserve.gov/econres/us-models-package.htm

Brummund, P. and M. R. Strain (2020). "Does Employment Respond Differently to Minimum Wage Increases in the Presence of Inflation Indexing?" *Journal of Human Resources* 55(3), 999–1024. DOI: 10.3368/jhr.55.2.1216.8404R2.

Burgess, S., E. Fernandez-Corugedo, C. Groth, R. Harrison, F. Monti, K. Theodoridis and M. Waldron (2013). "The Bank of England's forecasting platform: COMPASS, MAPS, EASE and the suite of models." *Bank of England Working Paper* 471. https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2013/the-boes-forecasting-platform-compass-maps-ease-and-the-suite-of-models.pdf

Card, D. (1986). "An Empirical Model of Wage Indexation Provisions in Union Contracts." *Journal of Political Economy* 94(3, Part 2), S144–S175. DOI: 10.1086/261402.

Cengiz, D., A. Dube, A. Lindner and B. Zipperer (2019). "The Effect of Minimum Wages on Low-Wage Jobs." *Quarterly Journal of Economics* 134(3), 1405–1454. DOI: 10.1093/qje/qjz014.

Checherita-Westphal, C. (ed.) and the Eurosystem Working Group on Public Finance (2022). "Public wage and pension indexation in the euro area: an overview." *ECB Occasional Paper* 299, August 2022. https://www.ecb.europa.eu/pub/pdf/scpops/ecb.op299~61d0565cfb.en.pdf

Coenen, G., P. Karadi, S. Schmidt and A. Warne (2018). "The New Area-Wide Model II." *ECB Working Paper* 2200. https://www.ecb.europa.eu/pub/pdf/scpwps/ecb.wp2200.en.pdf

Coibion, O., Y. Gorodnichenko and M. Weber (2020). "How Did U.S. Consumers Use Their Stimulus Payments?" *NBER Working Paper* 27693. https://ideas.repec.org/p/nbr/nberwo/27693.html

de Soyres, F., A. M. Santacreu and H. Young (2022). "Fiscal policy and excess inflation during Covid-19: a cross-country view." *FEDS Notes*, Board of Governors of the Federal Reserve System, 15 July 2022.

De Spiegelaere, S. (2023). "All rise: Automatic wage increases in collective agreements in Europe." UNI Europa Snapshot Report 2023-01. https://www.uni-europa.org/wp-content/uploads/sites/3/2023/04/22_02_2023_indexation-1.pdf

DeLuca, M. and W. Van Zandweghe (2023). "Postpandemic Nominal Wage Growth: Inflation Pass-Through or Labor Market Imbalance?" *Federal Reserve Bank of Cleveland Economic Commentary* 2023-13. DOI: 10.26509/frbc-ec-202313.

Destatis (2022). "Inflation rate at +10.0% in September 2022." Press release 438/2022. https://www.destatis.de/EN/Press/2022/10/PE22_438_611.html

Destatis (2025). "Mehr als acht von zehn Tarifbeschäftigten haben eine Inflationsausgleichsprämie erhalten." Pressemitteilung 023, 21 January 2025. https://www.destatis.de/DE/Presse/Pressemitteilungen/2025/01/PD25_023_622.html

di Giovanni, J., Ş. Kalemli-Özcan, A. Silva and M. A. Yıldırım (2022). "Global Supply Chain Pressures, International Trade, and Inflation." *NBER Working Paper* 30240. https://www.nber.org/papers/w30240

di Giovanni, J., Ş. Kalemli-Özcan, A. Silva and M. A. Yıldırım (2023). "Quantifying the Inflationary Impact of Fiscal Stimulus under Supply Constraints." *AEA Papers and Proceedings* 113, 76–80. DOI: 10.1257/pandp.20231028.

Dornbusch, R. and S. Edwards (eds.) (1991). *The Macroeconomics of Populism in Latin America*. NBER Conference Report, University of Chicago Press. https://www.nber.org/books-and-chapters/macroeconomics-populism-latin-america

Dube, A. (2019). *Impacts of Minimum Wages: Review of the International Evidence*. HM Treasury / BEIS, November 2019.

Dupor, B., M. Karabarbounis, M. Kudlyak and M. S. Mehkari (2023). "Regional Consumption Responses and the Aggregate Fiscal Multiplier." *Review of Economic Studies* 90(6), 2982–3021. DOI: 10.1093/restud/rdad007.

ECB (2022). "Minimum wages and their role for euro area wage growth." Box, *ECB Economic Bulletin* Issue 3/2022, 28 April 2022.

Ehrenberg, R. G., L. Danziger and G. San (1983). "Cost-of-Living Adjustment Clauses in Union Contracts: A Summary of Results." *Journal of Labor Economics* 1(3), 215–245. DOI: 10.1086/298011.

European Union (2022). Directive (EU) 2022/2041 of the European Parliament and of the Council of 19 October 2022 on adequate minimum wages in the European Union.

Eurostat (2022). "Treatment of Energy Prices Compensation Measures in the Harmonised Index of Consumer Prices (HICP)." Methodological note, Directorate C, 16 December 2022. https://ec.europa.eu/eurostat/documents/272892/11336726/Treatment-energy-prices-compensation-measures-HICP.pdf/

Fails, M. D. (2025). "Pain at the Pump, Pain at the Polls? Global Evidence on Election Timing, State Capacity, and Gasoline Prices." *Journal of Political Institutions and Political Economy* 6(1), 1–25. DOI: 10.1561/113.00000115.

Ferdinandusse, M. and M. Delgado-Téllez (2024). "Fiscal policy measures in response to the energy and inflation shock and climate change." Box, *ECB Economic Bulletin* Issue 1/2024. https://www.ecb.europa.eu/press/economic-bulletin/focus/2024/html/ecb.ebbox202401_08~d136db2a83.en.html

Fischer, S. (1977a). "Long-Term Contracts, Rational Expectations, and the Optimal Money Supply Rule." *Journal of Political Economy* 85(1), 191–205. DOI: 10.1086/260551.

Fischer, S. (1977b). "Wage indexation and macroeconomic stability." *Carnegie-Rochester Conference Series on Public Policy* 5, 107–147. DOI: 10.1016/0167-2231(77)90005-7.

Funke, M., M. Schularick and C. Trebesch (2023). "Populist Leaders and the Economy." *American Economic Review* 113(12), 3249–3288. DOI: 10.1257/aer.20202045.

Gagliardone, L. and M. Gertler (2023). "Oil Prices, Monetary Policy and Inflation Surges." *NBER Working Paper* 31263. DOI: 10.3386/w31263. (Forthcoming, *American Economic Journal: Macroeconomics*; the AEA DOI is not yet registered, so the working paper is cited.)

Galí, J. (2011). "The Return of the Wage Phillips Curve." *Journal of the European Economic Association* 9(3), 436–461. DOI: 10.1111/j.1542-4774.2011.01023.x.

Galí, J. and L. Gambetti (2020). "Has the U.S. Wage Phillips Curve Flattened? A Semi-Structural Exploration." In G. Castex, J. Galí and D. Saravia (eds.), *Changing Inflation Dynamics, Evolving Monetary Policy*, Central Bank of Chile, 149–171. Also *NBER Working Paper* 25476.

Geis, A., with Y. C. Wong and N. Vernon (2023). "Wage Indexation and International Competitiveness in Belgium: An Uneasy Coexistence." *IMF Selected Issues Paper* SIP/2023/015. https://www.imf.org/-/media/files/publications/selected-issues-papers/2023/english/sipea2023015.pdf

Glover, A. and J. Mustre-del-Río (2021). "What Happens When the Minimum Wage Rises? It Depends on Monetary Policy." *Federal Reserve Bank of Kansas City Economic Review*, Q3 2021.

Gopalan, R., B. H. Hamilton, A. Kalda and D. Sovich (2021). "State Minimum Wages, Employment, and Wage Spillovers: Evidence from Administrative Payroll Data." *Journal of Labor Economics* 39(3), 673–707. DOI: 10.1086/711355.

Górnicka, L. and G. Koester (eds.) (2023). "A forward-looking tracker of negotiated wages in the euro area." *ECB Occasional Paper* 338. https://www.ecb.europa.eu/pub/pdf/scpops/ecb.op338~dd97c1f69e.en.pdf

Gray, J. A. (1976). "Wage indexation: A macroeconomic approach." *Journal of Monetary Economics* 2(2), 221–235. DOI: 10.1016/0304-3932(76)90034-9.

Hahn, E. (2020). "The wage-price pass-through in the euro area: does the growth regime matter?" *ECB Working Paper* 2485. https://www.ecb.europa.eu/pub/pdf/scpwps/ecb.wp2485~ade2cab91e.en.pdf

Harasztosi, P. and A. Lindner (2019). "Who Pays for the Minimum Wage?" *American Economic Review* 109(8), 2693–2727. DOI: 10.1257/aer.20171445.

Haskel, J., J. Martin and L. Brandt (2023). "Recent UK inflation: an application of the Bernanke-Blanchard model." Bank of England, 27 November 2023. https://www.bankofengland.co.uk/-/media/boe/files/speech/2023/november/recent-uk-inflation-an-application-of-the-bernanke-blanchard-model-paper.pdf

Hendricks, W. E. and L. M. Kahn (1983). "Cost-of-Living Clauses in Union Contracts: Determinants and Effects." *Industrial and Labor Relations Review* 36(3), 447–460. DOI: 10.1177/001979398303600309.

Hidalgo-Pérez, M., N. Collado Van-Baumberghen, J. Galindo and R. Mateo Escobar (2023). "The Effects of the Spanish Gas Cap on Prices, Inflation, and Consumption Six Months Later." EsadeEcPol Insight 43. https://www.esade.edu/ecpol/wp-content/uploads/2023/02/AAFF_ENG_EsadeEcPol_Insight42_The-Effects-of-the-Gas-Cap-on-Prices-1.pdf

ILO (2024). "How has wage bargaining responded to the acceleration of inflation?" Factsheet, May 2024. https://www.ilo.org/sites/default/files/2024-05/Factsheet_Web%20format_How%20has%20wage%20bargaining%20responded%20to%20the%20acceleration%20of%20inflation.pdf

IMF (2022). "Wage Dynamics Post–COVID-19 and Wage-Price Spiral Risks." Chapter 2 in *World Economic Outlook: Countering the Cost-of-Living Crisis*, October 2022. https://www.imf.org/-/media/files/publications/weo/2022/october/english/ch2.pdf

Jadresic, E. (1996). "Wage Indexation and Macroeconomic Stability: The Gray–Fischer Theorem Revisited." *IMF Working Paper* 96/121. DOI: 10.5089/9781451854336.001.

Jannsen, N. and N. Sonnenberg (2023). "Inflation: Neues Basisjahr und Preisbremsen." *Wirtschaftsdienst* 103(3), 223–224. DOI: 10.2478/wd-2023-0058.

Jonckheere, J. and H. Zimmer (2024). "Wage-price dynamics and monetary policy." *NBB Economic Review* 2024/4. https://www.nbb.be/doc/ts/publications/economicreview/2024/ecorevi2024_h04.pdf

Jordà, Ò., C. Liu, F. Nechio and F. Rivera-Reyes (2022). "Why Is U.S. Inflation Higher than in Other Countries?" *FRBSF Economic Letter* 2022-07. https://www.frbsf.org/wp-content/uploads/el2022-07.pdf

Kindberg-Hanlon, G. (2024). "Transfers, Excess Savings, and Large Fiscal Multipliers." *IMF Working Paper* 24/208. https://www.imf.org/-/media/files/publications/wp/2024/english/wpiea2024208-print-pdf.pdf

Koester, G. and H. Grapow (2021). "The prevalence of private sector wage indexation in the euro area and its potential role for the impact of inflation on wages." Box, *ECB Economic Bulletin* Issue 7/2021. https://www.ecb.europa.eu/press/economic-bulletin/focus/2021/html/ecb.ebbox202107_07~f555b70c47.en.html

Komatsu, M. (2025). "To Cap or Not to Cap? Energy Crises in a Currency Union." *Federal Reserve Board International Finance Discussion Paper* 1428. DOI: 10.17016/IFDP.2025.1428.

Lacombe, J. and J. Borum (1987). "Major labor contracts in 1986 provided record low wage adjustments." *Monthly Labor Review*, May 1987. https://www.bls.gov/opub/mlr/1987/05/art2full.pdf

Lemoine, M., A. Petronevich and A. Zhutova (2024). "Bouclier tarifaire sur les prix de l'énergie en France : quel bilan ?" *Bulletin de la Banque de France* 253/4. https://www.banque-france.fr/system/files/2024-07/BDF253_4_Bouclier_tarifaire_web.pdf

Lemos, S. (2008). "A Survey of the Effects of the Minimum Wage on Prices." *Journal of Economic Surveys* 22(1), 187–212. DOI: 10.1111/j.1467-6419.2007.00532.x.

Leung, J. H. (2021). "Minimum Wage and Real Wage Inequality: Evidence from Pass-Through to Retail Prices." *Review of Economics and Statistics* 103(4), 754–769. DOI: 10.1162/rest_a_00915.

Lorenzoni, G. and I. Werning (2023). "Wage-Price Spirals." *Brookings Papers on Economic Activity*, Fall 2023, 317–393. DOI: 10.1353/eca.2023.a935427.

Low Pay Commission (2026). "Explainer: the minimum wage and inflation." 1 April 2026. https://minimumwage.blog.gov.uk/2026/04/01/low-pay-commission-explainer-the-minimum-wage-and-inflation

MaCurdy, T. (2015). "How Effective Is the Minimum Wage at Supporting the Poor?" *Journal of Political Economy* 123(2), 497–545. DOI: 10.1086/679626.

Manacorda, M. (2004). "Can the Scala Mobile Explain the Fall and Rise of Earnings Inequality in Italy? A Semiparametric Analysis, 1977–1993." *Journal of Labor Economics* 22(3), 585–614. DOI: 10.1086/383108.

Modigliani, F. and T. Padoa-Schioppa (1978). "The Management of an Open Economy with '100% Plus' Wage Indexation." *Essays in International Finance* 130, Princeton University. https://ies.princeton.edu/pdf/E130.pdf

ONS (2022a). "Treatment of the upcoming energy bill rebate in consumer price statistics." Statement, 28 February 2022. https://www.ons.gov.uk/news/statementsandletters/treatmentoftheupcomingenergybillrebateinconsumerpricestatistics

ONS (2022b). "Energy Bills Support Scheme classification." Statement, 31 August 2022. https://www.ons.gov.uk/news/statementsandletters/energybillssupportschemeclassification

ONS (2022c). "Classification review of the Energy Price Guarantee and Energy Bill Relief Scheme." Statement, 31 October 2022. https://www.ons.gov.uk/news/statementsandletters/classificationreviewoftheenergypriceguaranteeandenergybillreliefscheme

Orchard, J., V. A. Ramey and J. F. Wieland (2025). "Micro MPCs and Macro Counterfactuals: The Case of the 2008 Rebates." *Quarterly Journal of Economics* 140(3), 2001–2052. DOI: 10.1093/qje/qjaf015.

Parker, J. A., N. S. Souleles, D. S. Johnson and R. McClelland (2013). "Consumer Spending and the Economic Stimulus Payments of 2008." *American Economic Review* 103(6), 2530–2553. DOI: 10.1257/aer.103.6.2530.

Pastore, F. (2010). "Assessing the impact of incomes policy: the Italian experience." *International Journal of Manpower* 31(7), 793–817. DOI: 10.1108/01437721011081608.

Ragan, J. F. and B. Bratsberg (2000). "Un-COLA: Why Have Cost-of-Living Clauses Disappeared from Union Contracts and Will They Return?" *Southern Economic Journal* 67(2), 304–324. DOI: 10.1002/j.2325-8012.2000.tb00338.x.

Renkin, T., C. Montialoux and M. Siegenthaler (2022). "The Pass-Through of Minimum Wages into U.S. Retail Prices: Evidence from Supermarket Scanner Data." *Review of Economics and Statistics* 104(5), 890–908. DOI: 10.1162/rest_a_00981.

Rodriguez Contreras, R. and O. Molina (2023). *Tackling rising inflation in sectoral collective wage bargaining*. Eurofound, Publications Office of the EU. DOI: 10.2806/004554.

Sachs, J. and C. Wyplosz (1986). "The Economic Consequences of President Mitterrand." *Economic Policy* 1(2), 261–322. DOI: 10.2307/1344559.

Sgaravatti, G., S. Tagliapietra and C. Trasi (2024). "Europe's fiscal policy response to the energy crisis: lessons learned for a greener way out." *Energy Efficiency* 17, art. 90. DOI: 10.1007/s12053-024-10275-0.

Sgaravatti, G., S. Tagliapietra, C. Trasi and G. Zachmann (2023). "National fiscal policy responses to the energy crisis." Bruegel Datasets, final update 26 June 2023. DOI: 10.64153/LQHK8283.

Shapiro, A. H. (2023). "How Much Do Labor Costs Drive Inflation?" *FRBSF Economic Letter* 2023-13. https://www.frbsf.org/research-and-insights/publications/economic-letter/2023/05/how-much-do-labor-costs-drive-inflation/

Shapiro, A. H. (2024). "On the Existence of Wage-Price Spirals." Presented at the Hutchins Center conference, 18 January 2024. https://www.brookings.edu/wp-content/uploads/2024/03/Session-3_Wage-price-spiral-wage-compression.pdf

Stock, J. H. and M. W. Watson (2007). "Why Has U.S. Inflation Become Harder to Forecast?" *Journal of Money, Credit and Banking* 39(s1), 3–33. Working paper: *NBER Working Paper* 12324.

Wilcox, D. W. (1989). "Social Security Benefits, Consumption Expenditure, and the Life Cycle Hypothesis." *Journal of Political Economy* 97(2), 288–304.

### Statutes and statutory sources

- **United States.** Social Security Act s.215(i), created by P.L. 92-336 (1972); first automatic COLA June 1975. Congressional Research Service, *Social Security: Cost-of-Living Adjustments*, CRS Report 94-803. SSA Office of the Chief Actuary, COLA series, https://www.ssa.gov/oact/cola/colaseries.html
- **United Kingdom.** Social Security Administration Act 1992, s.150; triple lock from 2011/12, suspended for 2022/23. House of Commons Library briefings CBP-7812 and CBP-10403. National Minimum Wage Act 1998.
- **France.** Code de la sécurité sociale art. L161-25 (pension revalorisation). Code du travail arts. L3231-4 and L3231-5 (the SMIC formula). Ordonnance 58-1374 (1958) and Code monétaire et financier art. L112-2 (prohibition of general price indexation). Groupe d'experts SMIC, *Rapports* 2024 and 2025. CNAV circulaire 2025-29, 22 December 2025.
- **Germany.** Mindestlohngesetz s.9 (biennial decision of the *Mindestlohnkommission* under a backward-looking orientation to the collectively agreed wage index). *Rentenanpassungsformel* — wage component, contribution-rate factor and sustainability factor, with the *Rentengarantie* and the 48% *Niveauschutzklausel* binding from 2024; BMAS, Deutsche Rentenversicherung, Bundesrechnungshof (2025). §3 Nr. 11c EStG (*Inflationsausgleichsprämie*; parameters verified from practitioner sources rather than from the statute text).
- **European Union.** Directive (EU) 2022/2041 of 19 October 2022 on adequate minimum wages in the European Union.

---

**A note on what remains unverified.** Two gaps are carried forward rather than closed. We could not locate a peer-reviewed paper estimating the effect of the French 1983 *désindexation* on price–wage pass-through: the institutional record is solid and the econometrics appear not to exist. And the IMF Selected Issues Paper on the drivers of Hungarian inflation — the natural primary source for the *rezsicsökkentés* case discussed in the fiscal-loop section — could not be retrieved for this work, so that case is cited as a lead requiring primary-source verification rather than as evidence.

---

> Derived from public sources — see method. Estimates, not official publications.
> Not investment advice. · bzhmacro.com
