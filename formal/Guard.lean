import Overtake

/-!
# Formalisation of Section 6 (second group) of the revised manuscript

Results of `paper/sections/06_theory.tex` from line 260 on: the guard bound and its
corollaries, the timeout bound, the absolute bound, late charges, the floor and the
price of the guarantee.  The model (`Input`, `Sched`, `IsFCFS`, `In`, `Out`, `identity`,
`necessary`, ...) is imported unchanged from `Overtake.lean`.

A policy is represented by constraints on the schedule it produces.  The constraint of
the guard (`Sched.IsGuardWith`) is the dispatch rule of Algorithm `alg:guard`
(`paper/sections/05_scheduling.tex:103-110`); a base policy is not modelled at all, so
every theorem holds for every base policy, including a clairvoyant or randomised one.

Build: `Overtake.olean` must exist first, compiled from `formal/Overtake.lean`
(`lake env lean --root=<dir> -o <dir>/olean/Overtake.olean <dir>/Overtake.lean`), and this
file is compiled with `LEAN_PATH=<dir>/olean:$LEAN_PATH lean Guard.lean` inside
`lake env`.  See the report for the exact commands.
-/

open MeasureTheory Set Finset
open scoped Classical

noncomputable section

namespace Overtake

variable {J : Type} [Fintype J] [LinearOrder J] {I : Input J}

/-! ## The guard as a constraint on a schedule -/

namespace Sched

variable (Q : Sched I)

/-- `q` belongs to the waiting set `Q` at the dispatch decision that starts `j`
(Algorithm guard, lines 100-103 and 110): it has arrived by `s j` (arrivals at an instant
are added before the dispatches of that instant) and has not been started by an earlier
decision. -/
def waitingAt (q j : J) : Prop := I.a q ≤ Q.s j ∧ (q = j ∨ Q.prec j q)

/-- The counter of `q` at the decision that starts `j`, for a charging relation `ch`:
`ch c j` says that the completion of `c` has been added to the counter by that decision. -/
def _root_.Overtake.overC (I : Input J) (ch : J → J → Prop) (q j : J) : ℝ :=
  ∑ c ∈ univ.filter (fun c => q < c ∧ ch c j), I.C c

/-- Equation (eq:over): total cost of the jobs of higher rank completed by `t`. -/
def overT (q : J) (t : ℝ) : ℝ :=
  ∑ c ∈ univ.filter (fun c => q < c ∧ Q.s c + I.C c ≤ t), I.C c

/-- Algorithm guard, lines 95-99: every completion at or before the decision instant is
charged before the decision. -/
def doneBy (c j : J) : Prop := Q.s c + I.C c ≤ Q.s j

lemma overC_doneBy (q j : J) : overC I Q.doneBy q j = Q.overT q (Q.s j) := rfl

/-- `q` is eligible at the decision that starts `j` (line 104). -/
def elig (ch : J → J → Prop) (b : J → J → ℝ) (q j : J) : Prop :=
  Q.waitingAt q j ∧ b q j ≤ overC I ch q j

/-- Algorithm guard, lines 104-110: if the eligible set `E` is non-empty, the job started is
its earliest-arrived (minimum-rank) member; otherwise the base policy chooses freely.
`b q j` is the budget of `q` at the decision that starts `j`, so it may depend on the job,
on the time and on the decision. -/
def IsGuardWith (ch : J → J → Prop) (b : J → J → ℝ) : Prop :=
  ∀ j, (∃ q, Q.elig ch b q j) → Q.elig ch b j j ∧ ∀ q, Q.elig ch b q j → j ≤ q

/-- The guard of Algorithm guard with prompt charging. -/
def IsGuard (b : J → J → ℝ) : Prop := Q.IsGuardWith Q.doneBy b

/-- The budget rule respects the cap: `0 ≤ budget(q,t) ≤ B_max` for every waiting job and
every decision (06:271-272). -/
def RespectsCap (b : J → J → ℝ) (Bmax : ℝ) : Prop :=
  ∀ q j, Q.waitingAt q j → 0 ≤ b q j ∧ b q j ≤ Bmax

/-- The only property of a dispatch that the proof of the guard bound uses: a waiting job
of lower rank than the job started is not eligible. -/
def GuardProp (ch : J → J → Prop) (b : J → J → ℝ) : Prop :=
  ∀ q j, Q.waitingAt q j → q < j → overC I ch q j < b q j

lemma guardProp_of {ch : J → J → Prop} {b : J → J → ℝ} (h : Q.IsGuardWith ch b) :
    Q.GuardProp ch b := by
  intro q j hw hqj
  by_contra hc
  push Not at hc
  obtain ⟨_, hmin⟩ := h j ⟨q, hw, hc⟩
  exact absurd (hmin q ⟨hw, hc⟩) (not_le.mpr hqj)

lemma waitingAt_of_overtaker {i j : J} (hij : i < j) (hji : Q.prec j i) :
    Q.waitingAt i j :=
  ⟨(I.ha_mono hij.le).trans (Q.start_ge j), Or.inr hji⟩

lemma _root_.Overtake.overC_nonneg (ch : J → J → Prop) (q j : J) : 0 ≤ overC I ch q j :=
  sum_nonneg fun c _ => (I.hC_pos c).le

lemma In_nonneg (i : J) : 0 ≤ Q.In i := sum_nonneg fun c _ => (I.hC_pos c).le

lemma In_eq_zero (i : J) (h : ¬ ∃ c, i < c ∧ Q.prec c i) : Q.In i = 0 := by
  apply sum_eq_zero
  intro c hc
  rw [Finset.mem_filter] at hc
  exact absurd ⟨c, hc.2⟩ h

/-- The overtaker of `i` started last. -/
lemma last_overtaker (i : J) (h : ∃ c, i < c ∧ Q.prec c i) :
    ∃ j, i < j ∧ Q.prec j i ∧ ∀ c, i < c → Q.prec c i → c ≠ j → Q.prec c j := by
  set O := univ.filter (fun c => i < c ∧ Q.prec c i) with hO
  have hne : O.Nonempty := by
    obtain ⟨c, hc⟩ := h
    exact ⟨c, by simp [O, hc]⟩
  obtain ⟨j, hjO, hjmax⟩ := O.exists_max_image Q.ord hne
  simp only [O, Finset.mem_filter, Finset.mem_univ, true_and] at hjO
  refine ⟨j, hjO.1, hjO.2, fun c hc1 hc2 hcj => ?_⟩
  have hle := hjmax c (by simp [O, hc1, hc2])
  unfold prec
  rcases lt_or_eq_of_le hle with h' | h'
  · exact h'
  · exact absurd (Q.ord_inj h') hcj

/-- Splitting `In_i` at the last overtaker `j`: the charged overtakers, the uncharged ones
started before `j`, and `j` itself. -/
lemma In_split (ch : J → J → Prop) {i j : J}
    (hlast : ∀ c, i < c → Q.prec c i → c ≠ j → Q.prec c j) :
    Q.In i ≤ overC I ch i j
      + ∑ c ∈ univ.filter (fun c => i < c ∧ Q.prec c j ∧ ¬ ch c j), I.C c + I.C j := by
  unfold In overC
  rw [Finset.sum_filter, Finset.sum_filter, Finset.sum_filter]
  have hj : I.C j = ∑ c, (if c = j then I.C c else 0) := by
    rw [Finset.sum_ite_eq']; simp
  rw [hj, ← Finset.sum_add_distrib, ← Finset.sum_add_distrib]
  apply sum_le_sum
  intro c _
  have hC := (I.hC_pos c).le
  by_cases hA : i < c ∧ Q.prec c i
  · have hp' : c = j ∨ Q.prec c j := by
      by_cases hcj : c = j
      · exact Or.inl hcj
      · exact Or.inr (hlast c hA.1 hA.2 hcj)
    split_ifs <;> first | linarith | (exfalso; tauto)
  · split_ifs <;> linarith

/-- Jobs in service at `s j`, other than `j`, sit on distinct servers other than `j`'s, so
their costs add up to at most `(k-1)L`. -/
lemma sum_running_le (j : J) (T : Finset J)
    (hT : ∀ c ∈ T, Q.running c (Q.s j) ∧ c ≠ j) :
    ∑ c ∈ T, I.C c ≤ ((I.k : ℝ) - 1) * I.L := by
  have hT' : ∀ c ∈ T, Q.running c (Q.s j) ∧ Q.srv c ≠ Q.srv j := by
    intro c hc
    refine ⟨(hT c hc).1, fun hsrv => ?_⟩
    have hr := (hT c hc).1
    unfold running at hr
    have hCj := I.hC_pos j
    rcases Q.no_overlap c j (hT c hc).2 hsrv with h | h <;> linarith
  have hc := Q.card_running_le (Q.s j) (Q.srv j) T hT'
  have hc' : (T.card : ℝ) ≤ (I.k : ℝ) - 1 := by
    have : ((T.card : ℕ) : ℝ) ≤ ((I.k - 1 : ℕ) : ℝ) := by exact_mod_cast hc
    rwa [Nat.cast_sub (Nat.succ_le_of_lt I.hk), Nat.cast_one] at this
  calc ∑ c ∈ T, I.C c ≤ ∑ _c ∈ T, I.L := sum_le_sum fun c _ => I.hC_le c
    _ = (T.card : ℝ) * I.L := by simp
    _ ≤ ((I.k : ℝ) - 1) * I.L := mul_le_mul_of_nonneg_right hc' I.hL.le

end Sched

/-- From a bound on `In_i` to a bound on the excess, through Theorem "Net-overtake
identity" with `Out_i ≥ 0`; a job without overtakers has `In_i = 0`. -/
lemma excess_lt_of_In (P F : Sched I) (hF : IsFCFS F) (i : J) (X : ℝ) (hX : 0 < X)
    (h : (∃ c, i < c ∧ P.prec c i) → P.In i < X) :
    excess P F i < X / I.k + (2 - 2 / (I.k : ℝ)) * I.L := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hIn : P.In i < X := by
    by_cases hc : ∃ c, i < c ∧ P.prec c i
    · exact h hc
    · rw [P.In_eq_zero i hc]; exact hX
  have hb := identity_bound P F hF i
  rw [abs_le] at hb
  unfold Delta at hb
  have hO := Out_nonneg P i
  have e : X / I.k + (2 - 2 / (I.k : ℝ)) * I.L = (X + 2 * ((I.k : ℝ) - 1) * I.L) / I.k := by
    field_simp
  rw [e, lt_div_iff₀ hk]
  unfold excess
  nlinarith [hb.2]

/-! ## Theorem "Guard bound" (06_theory.tex:269) -/

lemma Sched.unch_running (P : Sched I) (i j : J) :
    ∀ c ∈ univ.filter (fun c => i < c ∧ P.prec c j ∧ ¬ P.doneBy c j),
      P.running c (P.s j) ∧ c ≠ j := by
  intro c hc
  rw [Finset.mem_filter] at hc
  obtain ⟨_, _, hp, hd⟩ := hc
  unfold Sched.doneBy at hd
  refine ⟨⟨P.s_le_of_prec hp, by linarith⟩, fun hcj => ?_⟩
  rw [hcj] at hp
  exact P.prec_irrefl j hp

/-- The core of the guard bound: at the decision that starts the last overtaker `j` of
`i`, the account of `i` is below its budget, and `In_i` exceeds the account by less than
`kL`. -/
theorem guard_In_at (P : Sched I) (b : J → J → ℝ) (hG : P.GuardProp P.doneBy b) (i : J)
    (h : ∃ c, i < c ∧ P.prec c i) :
    ∃ j, P.waitingAt i j ∧ P.s j ≤ P.s i ∧ P.In i < b i j + I.k * I.L := by
  obtain ⟨j, hij, hji, hlast⟩ := P.last_overtaker i h
  have hw := P.waitingAt_of_overtaker hij hji
  refine ⟨j, hw, P.s_le_of_prec hji, ?_⟩
  have h1 := P.In_split P.doneBy hlast
  have h2 := hG i j hw hij
  have h4 : ∑ c ∈ univ.filter (fun c => i < c ∧ P.prec c j ∧ ¬ P.doneBy c j), I.C c
      ≤ ((I.k : ℝ) - 1) * I.L := by
    exact P.sum_running_le j _ (P.unch_running i j)
  have h5 := I.hC_le j
  nlinarith

/-- Inequality (eq:guardin) for any dispatch rule with the property `GuardProp` under
prompt charging. -/
theorem guard_In_of_prop (P : Sched I) (b : J → J → ℝ) (Bmax : ℝ)
    (hcap : ∀ q j, P.waitingAt q j → b q j ≤ Bmax) (hG : P.GuardProp P.doneBy b) (i : J)
    (h : ∃ c, i < c ∧ P.prec c i) : P.In i < Bmax + I.k * I.L := by
  obtain ⟨j, hw, _, hlt⟩ := guard_In_at P b hG i h
  linarith [hcap i j hw]

/-- Theorem "Guard bound", inequality (eq:guardin): `In_i < B_max + kL` whenever `i` has an
overtaker. -/
theorem guard_In (P : Sched I) (b : J → J → ℝ) (Bmax : ℝ) (hcap : P.RespectsCap b Bmax)
    (hG : P.IsGuard b) (i : J) (h : ∃ c, i < c ∧ P.prec c i) :
    P.In i < Bmax + I.k * I.L :=
  guard_In_of_prop P b Bmax (fun q j hw => (hcap q j hw).2) (P.guardProp_of hG) i h

lemma guard_excess_of_In (P F : Sched I) (hF : IsFCFS F) (Bmax : ℝ) (hB : 0 ≤ Bmax) (i : J)
    (h : (∃ c, i < c ∧ P.prec c i) → P.In i < Bmax + I.k * I.L) :
    P.W i < F.W i + Bmax / I.k + (3 - 2 / (I.k : ℝ)) * I.L := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hX : 0 < Bmax + I.k * I.L := by nlinarith [I.hL]
  have := excess_lt_of_In P F hF i _ hX h
  unfold excess at this
  have e : (Bmax + I.k * I.L) / I.k = Bmax / I.k + I.L := by field_simp
  rw [e] at this
  linarith

/-- Theorem "Guard bound", inequality (eq:guardadd):
`W < W_FCFS[i] + B_max/k + (3 - 2/k)L` for every job. -/
theorem guard_bound (P F : Sched I) (hF : IsFCFS F) (b : J → J → ℝ) (Bmax : ℝ)
    (hB : 0 ≤ Bmax) (hcap : P.RespectsCap b Bmax) (hG : P.IsGuard b) (i : J) :
    P.W i < F.W i + Bmax / I.k + (3 - 2 / (I.k : ℝ)) * I.L :=
  guard_excess_of_In P F hF Bmax hB i (guard_In P b Bmax hcap hG i)

/-- Reports counted twice (06:514-517): the guard of Algorithm guard run on any counter
`cnt` that is at least the true account (`over`) keeps inequality (eq:guardadd). -/
theorem guard_bound_dup (P F : Sched I) (hF : IsFCFS F) (b : J → J → ℝ) (Bmax : ℝ)
    (hB : 0 ≤ Bmax) (hcap : P.RespectsCap b Bmax) (cnt : J → J → ℝ)
    (hcnt : ∀ q j, P.waitingAt q j → P.overT q (P.s j) ≤ cnt q j)
    (hG : ∀ j, (∃ q, P.waitingAt q j ∧ b q j ≤ cnt q j) →
      (P.waitingAt j j ∧ b j j ≤ cnt j j) ∧
      ∀ q, P.waitingAt q j ∧ b q j ≤ cnt q j → j ≤ q) (i : J) :
    P.W i < F.W i + Bmax / I.k + (3 - 2 / (I.k : ℝ)) * I.L := by
  have hP : P.GuardProp P.doneBy b := by
    intro q j hw hqj
    rw [P.overC_doneBy]
    by_contra hc
    push Not at hc
    have hq : P.waitingAt q j ∧ b q j ≤ cnt q j := ⟨hw, hc.trans (hcnt q j hw)⟩
    exact absurd ((hG j ⟨q, hq⟩).2 q hq) (not_le.mpr hqj)
  exact guard_excess_of_In P F hF Bmax hB i
    (guard_In_of_prop P b Bmax (fun q j hw => (hcap q j hw).2) hP i)

/-! ## Corollary "The cap for a given bound" (06_theory.tex:307) -/

/-- With `B_max = k(G - (3 - 2/k)L)` and `G ≥ (3 - 2/k)L` the guard offers the guarantee
`G` (strictly). -/
theorem cap_for_bound (P F : Sched I) (hF : IsFCFS F) (b : J → J → ℝ) (G : ℝ)
    (hG3 : (3 - 2 / (I.k : ℝ)) * I.L ≤ G)
    (hcap : P.RespectsCap b (I.k * (G - (3 - 2 / (I.k : ℝ)) * I.L))) (hG : P.IsGuard b)
    (i : J) : excess P F i < G := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hB : 0 ≤ (I.k : ℝ) * (G - (3 - 2 / (I.k : ℝ)) * I.L) :=
    mul_nonneg hk.le (by linarith)
  have := guard_bound P F hF b _ hB hcap hG i
  unfold excess
  have e : (I.k : ℝ) * (G - (3 - 2 / (I.k : ℝ)) * I.L) / I.k = G - (3 - 2 / (I.k : ℝ)) * I.L := by
    field_simp
  rw [e] at this
  linarith

/-- The cap is positive exactly when `G > (3 - 2/k)L`. -/
lemma cap_pos_iff (G : ℝ) :
    0 < (I.k : ℝ) * (G - (3 - 2 / (I.k : ℝ)) * I.L) ↔ (3 - 2 / (I.k : ℝ)) * I.L < G := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  constructor
  · intro h
    by_contra h'
    push Not at h'
    nlinarith
  · intro h
    exact mul_pos hk (by linarith)

namespace Sched

variable (Q : Sched I)

/-- At no decision does a job of lower rank wait, if every waiting job with an empty
account is eligible (S4.8, the degenerate case). -/
lemma no_lower_waiting (b : J → J → ℝ) (hG : Q.IsGuard b)
    (hb : ∀ q j, Q.waitingAt q j → Q.overT q (Q.s j) = 0 → b q j ≤ 0) :
    ∀ n, ∀ j q, Q.ord j = n → Q.waitingAt q j → ¬ q < j := by
  intro n
  induction n using Nat.strong_induction_on with
  | _ n ih =>
  intro j q hjn hw hqj
  have hover : Q.overT q (Q.s j) = 0 := by
    apply sum_eq_zero
    intro c hc
    exfalso
    simp only [Finset.mem_filter, Finset.mem_univ, true_and] at hc
    have hCc := I.hC_pos c
    have hscj : Q.s c < Q.s j := by linarith [hc.2]
    have hord : Q.ord c < Q.ord j := Q.ord_refines j c hscj
    have hwc : Q.waitingAt q c := by
      refine ⟨(I.ha_mono hc.1.le).trans (Q.start_ge c), Or.inr ?_⟩
      rcases hw.2 with h | h
      · exact absurd h (ne_of_lt hqj)
      · exact lt_trans hord h
    exact ih (Q.ord c) (hjn ▸ hord) c q rfl hwc hc.1
  have hel : Q.elig Q.doneBy b q j := ⟨hw, by
    rw [Q.overC_doneBy, hover]; exact hb q j hw hover⟩
  obtain ⟨_, hmin⟩ := hG j ⟨q, hel⟩
  exact absurd (hmin q hel) (not_le.mpr hqj)

end Sched

/-- A budget rule that gives budget `0` to every job whose account is empty (in particular
`B_max = 0`, the equality case of Corollary "The cap for a given bound") makes the guard
first-come first-served, whatever the base policy. -/
theorem guard_fcfs_of_zero (P : Sched I) (b : J → J → ℝ) (hG : P.IsGuard b)
    (hb : ∀ q j, P.waitingAt q j → P.overT q (P.s j) = 0 → b q j ≤ 0) : IsFCFS P := by
  have K := fun j q => P.no_lower_waiting b hG hb (P.ord j) j q rfl
  intro i j
  constructor
  · intro h
    by_contra hji
    have hij : i < j := lt_of_le_of_ne (not_lt.mp hji) (fun e => by subst e; exact lt_irrefl _ h)
    exact K j i (P.waitingAt_of_overtaker hij h) hij
  · intro hji
    rcases P.prec_total (ne_of_gt hji) with h | h
    · exact h
    · exact absurd hji (K i j ⟨(I.ha_mono hji.le).trans (P.start_ge i), Or.inr h⟩)

/-- Corollary "The cap for a given bound", the equality case: `B_max = 0` gives FCFS. -/
theorem guard_cap_zero_fcfs (P : Sched I) (b : J → J → ℝ) (hcap : P.RespectsCap b 0)
    (hG : P.IsGuard b) : IsFCFS P :=
  guard_fcfs_of_zero P b hG fun q j hw _ => (hcap q j hw).2

/-! ## The budget family (eq:budget) respects the cap -/

/-- `budget(q,t) = min(B_0 + γ n_q + η k (t - a_q), B_max)`. -/
def budgetFamily (B0 γ η Bmax : ℝ) (n : J → ℕ) (q : J) (t : ℝ) : ℝ :=
  min (B0 + γ * n q + η * I.k * (t - I.a q)) Bmax

lemma budgetFamily_cap (B0 γ η Bmax : ℝ) (n : J → ℕ) (hB0 : 0 ≤ B0) (hγ : 0 ≤ γ)
    (hη : 0 ≤ η) (hB : 0 ≤ Bmax) (q : J) (t : ℝ) (ht : I.a q ≤ t) :
    0 ≤ budgetFamily (I := I) B0 γ η Bmax n q t ∧ budgetFamily (I := I) B0 γ η Bmax n q t ≤ Bmax := by
  have hk : (0 : ℝ) ≤ I.k := by positivity
  refine ⟨le_min ?_ hB, min_le_right _ _⟩
  have h1 : 0 ≤ γ * (n q : ℝ) := mul_nonneg hγ (by positivity)
  have h2 : 0 ≤ η * I.k * (t - I.a q) := mul_nonneg (mul_nonneg hη hk) (by linarith)
  linarith

/-- The family, read at the decision that starts `j`, respects the cap. -/
lemma budgetFamily_respects (P : Sched I) (B0 γ η Bmax : ℝ) (n : J → ℕ) (hB0 : 0 ≤ B0)
    (hγ : 0 ≤ γ) (hη : 0 ≤ η) (hB : 0 ≤ Bmax) :
    P.RespectsCap (fun q j => budgetFamily (I := I) B0 γ η Bmax n q (P.s j)) Bmax :=
  fun q j hw => budgetFamily_cap B0 γ η Bmax n hB0 hγ hη hB q (P.s j) hw.1

/-! ## The multiplicative bound for the age-relative shape (06_theory.tex:346-348, S4.5) -/

theorem guard_mult (P F : Sched I) (hF : IsFCFS F) (b : J → J → ℝ) (B0 η : ℝ)
    (hB0 : 0 ≤ B0) (hη0 : 0 ≤ η) (_hη1 : η < 1)
    (hb : ∀ q j, P.waitingAt q j → b q j ≤ B0 + η * I.k * (P.s j - I.a q))
    (hG : P.IsGuard b) (i : J) :
    (1 - η) * P.W i < F.W i + B0 / I.k + (3 - 2 / (I.k : ℝ)) * I.L := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hW : 0 ≤ P.W i := by unfold Sched.W; linarith [P.start_ge i]
  set X := B0 + η * I.k * P.W i + I.k * I.L with hX
  have hXpos : 0 < X := by
    have : 0 ≤ η * I.k * P.W i := mul_nonneg (mul_nonneg hη0 hk.le) hW
    nlinarith [I.hL]
  have hIn : (∃ c, i < c ∧ P.prec c i) → P.In i < X := by
    intro h
    obtain ⟨j, hw, hsj, hlt⟩ := guard_In_at P b (P.guardProp_of hG) i h
    have h1 := hb i j hw
    have h3 : η * I.k * (P.s j - I.a i) ≤ η * I.k * P.W i := by
      unfold Sched.W
      exact mul_le_mul_of_nonneg_left (by linarith) (mul_nonneg hη0 hk.le)
    linarith
  have := excess_lt_of_In P F hF i X hXpos hIn
  unfold excess at this
  have e : X / I.k = B0 / I.k + η * P.W i + I.L := by
    rw [hX]; field_simp
  rw [e] at this
  linarith

/-! ## Proposition "Timeout bound" (06_theory.tex:371) -/

namespace Sched

variable (Q : Sched I)

/-- `h` is the earliest-arrived (minimum-rank) job waiting at the decision that starts `j`. -/
def isHead (h j : J) : Prop := Q.waitingAt h j ∧ ∀ q, Q.waitingAt q j → h ≤ q

/-- Timeout(θ) (06:366-368): once the earliest-arrived waiting job has waited `θ`, it is
started next; otherwise the base policy decides (no constraint). -/
def IsTimeout (θ : ℝ) : Prop := ∀ j h, Q.isHead h j → θ ≤ Q.s j - I.a h → j = h

/-- The combined rule (06:406-407): start the earliest-arrived job if it has waited `θ`,
and otherwise run Algorithm guard with charging relation `ch`. -/
def IsCombined (θ : ℝ) (ch : J → J → Prop) (b : J → J → ℝ) : Prop := ∀ j,
  (∀ h, Q.isHead h j → θ ≤ Q.s j - I.a h → j = h) ∧
  ((¬ ∃ h, Q.isHead h j ∧ θ ≤ Q.s j - I.a h) →
    (∃ q, Q.elig ch b q j) → Q.elig ch b j j ∧ ∀ q, Q.elig ch b q j → j ≤ q)

lemma head_exists {q j : J} (hq : Q.waitingAt q j) : ∃ h, Q.isHead h j := by
  set S := univ.filter (fun q => Q.waitingAt q j)
  have hne : S.Nonempty := ⟨q, by simp [S, hq]⟩
  obtain ⟨h, hS, hmin⟩ := S.exists_min_image id hne
  rw [Finset.mem_filter] at hS
  exact ⟨h, hS.2, fun q' hq' => hmin q' (by simp [S, hq'])⟩

lemma timeout_start_lt {θ : ℝ} (hT : Q.IsTimeout θ) {i c : J} (hic : i < c)
    (hci : Q.prec c i) : Q.s c < I.a i + θ := by
  by_contra hge
  push Not at hge
  obtain ⟨h, hh⟩ := Q.head_exists (Q.waitingAt_of_overtaker hic hci)
  have hhi : h ≤ i := hh.2 i (Q.waitingAt_of_overtaker hic hci)
  have hai : I.a h ≤ I.a i := I.ha_mono hhi
  have := hT c h hh (by linarith)
  subst this
  exact absurd hhi (not_le.mpr hic)

/-- If every overtaker of `i` starts in `[u, v]`, then `In_i ≤ k (v - u + L)`. -/
lemma In_le_window (i : J) (u v : ℝ) (huv : u ≤ v)
    (hwin : ∀ c, i < c → Q.prec c i → u ≤ Q.s c ∧ Q.s c ≤ v) :
    Q.In i ≤ (I.k : ℝ) * (v - u + I.L) := by
  unfold In
  rw [← Finset.sum_fiberwise _ Q.srv]
  calc ∑ m, ∑ j ∈ (univ.filter (fun j => i < j ∧ Q.prec j i)).filter
          (fun j => Q.srv j = m), I.C j
      ≤ ∑ _m : Fin I.k, (v - u + I.L) := by
        apply sum_le_sum
        intro m _
        have := Q.server_sum_le m (univ.filter (fun j => i < j ∧ Q.prec j i))
          (fun j => Ico (Q.s j) (Q.s j + I.C j)) (fun j => subset_rfl)
          (fun j => measurableSet_Ico) (Ico u (v + I.L))
          measure_Ico_lt_top.ne (by
            intro j hj _
            rw [Finset.mem_filter] at hj
            have h := hwin j hj.2.1 hj.2.2
            apply Set.Ico_subset_Ico h.1
            linarith [I.hC_le j])
        simp only [vol_job] at this
        rw [Real.volume_real_Ico, max_eq_left (by linarith [I.hL])] at this
        linarith
    _ = (I.k : ℝ) * (v - u + I.L) := by simp [mul_add]

end Sched

/-- Proposition "Timeout bound", first part: `In_i < k(θ + L)` for a job with an
overtaker. -/
theorem timeout_In (P : Sched I) (θ : ℝ) (hT : P.IsTimeout θ) (i : J)
    (h : ∃ c, i < c ∧ P.prec c i) : P.In i < (I.k : ℝ) * (θ + I.L) := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  set O := univ.filter (fun c => i < c ∧ P.prec c i)
  have hne : O.Nonempty := by
    obtain ⟨c, hc⟩ := h
    exact ⟨c, by simp [O, hc]⟩
  obtain ⟨c0, hc0, hmax⟩ := O.exists_max_image P.s hne
  simp only [O, Finset.mem_filter, Finset.mem_univ, true_and] at hc0
  have hlt := P.timeout_start_lt hT hc0.1 hc0.2
  have hu : I.a i ≤ P.s c0 := (I.ha_mono hc0.1.le).trans (P.start_ge c0)
  have hle := P.In_le_window i (I.a i) (P.s c0) hu (fun c hc1 hc2 =>
    ⟨(I.ha_mono hc1.le).trans (P.start_ge c), hmax c (by simp [O, hc1, hc2])⟩)
  have : (I.k : ℝ) * (P.s c0 - I.a i + I.L) < (I.k : ℝ) * (θ + I.L) :=
    mul_lt_mul_of_pos_left (by linarith) hk
  linarith

/-- Proposition "Timeout bound", inequality (eq:clock). -/
theorem timeout_bound (P F : Sched I) (hF : IsFCFS F) (θ : ℝ) (hθ : 0 ≤ θ)
    (hT : P.IsTimeout θ) (i : J) :
    P.W i < F.W i + θ + (3 - 2 / (I.k : ℝ)) * I.L := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hX : 0 < (I.k : ℝ) * (θ + I.L) := mul_pos hk (by linarith [I.hL])
  have := excess_lt_of_In P F hF i _ hX (timeout_In P θ hT i)
  unfold excess at this
  have e : (I.k : ℝ) * (θ + I.L) / I.k = θ + I.L := by field_simp
  rw [e] at this
  linarith

/-- The combined rule obeys the clock part. -/
lemma Sched.combined_timeout (P : Sched I) {θ : ℝ} {ch : J → J → Prop} {b : J → J → ℝ}
    (h : P.IsCombined θ ch b) : P.IsTimeout θ :=
  fun j hh hhd hθ => (h j).1 hh hhd hθ

/-- The combined rule has the guard property, for any charging relation. -/
lemma Sched.combined_guardProp (P : Sched I) {θ : ℝ} {ch : J → J → Prop} {b : J → J → ℝ}
    (h : P.IsCombined θ ch b) : P.GuardProp ch b := by
  intro q j hw hqj
  by_contra hc
  push Not at hc
  by_cases hclk : ∃ h, P.isHead h j ∧ θ ≤ P.s j - I.a h
  · obtain ⟨hh, hhd, hθ⟩ := hclk
    have := (h j).1 hh hhd hθ
    subst this
    exact absurd (hhd.2 q hw) (not_le.mpr hqj)
  · obtain ⟨_, hmin⟩ := (h j).2 hclk ⟨q, hw, hc⟩
    exact absurd (hmin q ⟨hw, hc⟩) (not_le.mpr hqj)

/-- The combined rule (06:406-410), with prompt charging: both bounds hold at once. -/
theorem combined_bounds (P F : Sched I) (hF : IsFCFS F) (θ : ℝ) (hθ : 0 ≤ θ)
    (b : J → J → ℝ) (Bmax : ℝ) (hB : 0 ≤ Bmax) (hcap : P.RespectsCap b Bmax)
    (h : P.IsCombined θ P.doneBy b) (i : J) :
    P.W i < F.W i + Bmax / I.k + (3 - 2 / (I.k : ℝ)) * I.L ∧
    P.W i < F.W i + θ + (3 - 2 / (I.k : ℝ)) * I.L :=
  ⟨guard_excess_of_In P F hF Bmax hB i
      (guard_In_of_prop P b Bmax (fun q j hw => (hcap q j hw).2) (P.combined_guardProp h) i),
    timeout_bound P F hF θ hθ (P.combined_timeout h) i⟩

/-- The clock part of the combined rule reads no completion report, so it holds for any
charging relation, in particular for reports that arrive late or never (06:409-410). -/
theorem combined_clock_any_reports (P F : Sched I) (hF : IsFCFS F) (θ : ℝ) (hθ : 0 ≤ θ)
    (ch : J → J → Prop) (b : J → J → ℝ) (h : P.IsCombined θ ch b) (i : J) :
    P.W i < F.W i + θ + (3 - 2 / (I.k : ℝ)) * I.L :=
  timeout_bound P F hF θ hθ (P.combined_timeout h) i

/-! ## Proposition "Late charges" (06_theory.tex:466) -/

namespace Sched

variable (Q : Sched I)

/-- Charges delayed by at most `δ` (06:463-465, S4.12): a counted charge belongs to a job
completed by the decision, and a completion is counted at every decision at least `δ`
after it.  `ch c j` may otherwise depend arbitrarily on the decision. -/
def DelayedCharges (ch : J → J → Prop) (δ : ℝ) : Prop :=
  (∀ c j, ch c j → Q.s c + I.C c ≤ Q.s j) ∧ (∀ c j, Q.s c + I.C c + δ ≤ Q.s j → ch c j)

/-- The model of S4.12: the charge of `c` reaches the counter at `f_c + d_c`,
`0 ≤ d_c ≤ δ`, before the dispatches of that instant. -/
lemma delayedCharges_of_d (δ : ℝ) (d : J → ℝ) (hd0 : ∀ c, 0 ≤ d c) (hdδ : ∀ c, d c ≤ δ) :
    Q.DelayedCharges (fun c j => Q.s c + I.C c + d c ≤ Q.s j) δ :=
  ⟨fun c j h => by linarith [hd0 c], fun c j h => by linarith [hdδ c]⟩

/-- Per-server views (06:501-503): the server that takes `j` sees its own completions at
once, others within `δ`. -/
def PerServerCharges (ch : J → J → Prop) (δ : ℝ) : Prop :=
  Q.DelayedCharges ch δ ∧ ∀ c j, Q.srv c = Q.srv j → Q.s c + I.C c ≤ Q.s j → ch c j

/-- Report before pull (06:476-479): a counted charge belongs to a completed job, a charge
once counted stays counted, and each server's own report is counted at its next pull.
Nothing bounds the delay of other servers' reports; they may never arrive. -/
def ReportBeforePull (ch : J → J → Prop) : Prop :=
  (∀ c j, ch c j → Q.s c + I.C c ≤ Q.s j) ∧
  (∀ c j j', ch c j → Q.ord j < Q.ord j' → ch c j') ∧
  (∀ c j, c ≠ j → Q.srv c = Q.srv j → Q.s c + I.C c ≤ Q.s j → ch c j)

/-- Stale jobs of one server (completed in `(t - δ, t]`) hold at most `L + δ`. -/
lemma stale_server_le (m : Fin I.k) (t δ : ℝ) (hδ : 0 ≤ δ) (T : Finset J)
    (hT : ∀ c ∈ T, Q.srv c = m ∧ Q.s c + I.C c ≤ t ∧ t < Q.s c + I.C c + δ) :
    ∑ c ∈ T, I.C c ≤ I.L + δ := by
  rcases T.eq_empty_or_nonempty with hE | hne
  · rw [hE, Finset.sum_empty]; linarith [I.hL]
  obtain ⟨c1, hc1, hmin⟩ := T.exists_min_image Q.s hne
  have := Q.server_sum_le m T (fun j => Ico (Q.s j) (Q.s j + I.C j)) (fun j => subset_rfl)
    (fun j => measurableSet_Ico) (Ico (Q.s c1) t) measure_Ico_lt_top.ne (by
      intro j hj _
      exact Set.Ico_subset_Ico (hmin j hj) (hT j hj).2.1)
  have hf : T.filter (fun j => Q.srv j = m) = T :=
    Finset.filter_true_of_mem fun j hj => (hT j hj).1
  rw [hf] at this
  simp only [vol_job] at this
  have h1 := hT c1 hc1
  rw [Real.volume_real_Ico, max_eq_left (by linarith [I.hC_pos c1])] at this
  linarith [I.hC_le c1]

/-- Sum over servers of a per-server bound. -/
lemma sum_by_server_le (T : Finset J) (B : ℝ)
    (hB : ∀ m, ∑ c ∈ T.filter (fun c => Q.srv c = m), I.C c ≤ B) :
    ∑ c ∈ T, I.C c ≤ (I.k : ℝ) * B := by
  rw [← Finset.sum_fiberwise T Q.srv]
  calc ∑ m, ∑ c ∈ T.filter (fun c => Q.srv c = m), I.C c ≤ ∑ _m : Fin I.k, B :=
        sum_le_sum fun m _ => hB m
    _ = (I.k : ℝ) * B := by simp

/-- Sum over servers, when one server `m0` contributes nothing. -/
lemma sum_by_server_le_erase (T : Finset J) (B : ℝ) (m0 : Fin I.k)
    (h0 : ∀ c ∈ T, Q.srv c ≠ m0)
    (hB : ∀ m, ∑ c ∈ T.filter (fun c => Q.srv c = m), I.C c ≤ B) :
    ∑ c ∈ T, I.C c ≤ ((I.k : ℝ) - 1) * B := by
  rw [← Finset.sum_fiberwise T Q.srv, ← Finset.add_sum_erase _ _ (Finset.mem_univ m0)]
  have hz : ∑ c ∈ T.filter (fun c => Q.srv c = m0), I.C c = 0 := by
    apply sum_eq_zero
    intro c hc
    rw [Finset.mem_filter] at hc
    exact absurd hc.2 (h0 c hc.1)
  rw [hz, zero_add]
  have hcard : ((univ.erase m0).card : ℝ) = (I.k : ℝ) - 1 := by
    rw [Finset.card_erase_of_mem (Finset.mem_univ _), Finset.card_univ, Fintype.card_fin,
      Nat.cast_sub (Nat.succ_le_of_lt I.hk), Nat.cast_one]
  calc ∑ m ∈ univ.erase m0, ∑ c ∈ T.filter (fun c => Q.srv c = m), I.C c
      ≤ ∑ _m ∈ univ.erase m0, B := sum_le_sum fun m _ => hB m
    _ = ((I.k : ℝ) - 1) * B := by rw [Finset.sum_const, nsmul_eq_mul, hcard]

/-- Uncharged overtakers started before `j`, split into those in service at `s j` and the
stale ones. -/
lemma unch_split (ch : J → J → Prop) (i j : J) :
    ∑ c ∈ univ.filter (fun c => i < c ∧ Q.prec c j ∧ ¬ ch c j), I.C c =
      ∑ c ∈ (univ.filter (fun c => i < c ∧ Q.prec c j ∧ ¬ ch c j)).filter
          (fun c => Q.running c (Q.s j)), I.C c +
      ∑ c ∈ (univ.filter (fun c => i < c ∧ Q.prec c j ∧ ¬ ch c j)).filter
          (fun c => ¬ Q.running c (Q.s j)), I.C c :=
  (Finset.sum_filter_add_sum_filter_not _ _ _).symm

lemma unch_run_le (ch : J → J → Prop) (i j : J) :
    ∑ c ∈ (univ.filter (fun c => i < c ∧ Q.prec c j ∧ ¬ ch c j)).filter
        (fun c => Q.running c (Q.s j)), I.C c ≤ ((I.k : ℝ) - 1) * I.L := by
  apply Q.sum_running_le j
  intro c hc
  rw [Finset.mem_filter, Finset.mem_filter] at hc
  refine ⟨hc.2, fun hcj => ?_⟩
  rw [hcj] at hc
  exact Q.prec_irrefl j hc.1.2.2.1

lemma unch_stale (ch : J → J → Prop) (δ : ℝ) (hD : Q.DelayedCharges ch δ) (i j : J) :
    ∀ c ∈ (univ.filter (fun c => i < c ∧ Q.prec c j ∧ ¬ ch c j)).filter
        (fun c => ¬ Q.running c (Q.s j)),
      Q.s c + I.C c ≤ Q.s j ∧ Q.s j < Q.s c + I.C c + δ ∧ ¬ ch c j := by
  intro c hc
  rw [Finset.mem_filter, Finset.mem_filter] at hc
  obtain ⟨⟨_, _, hp, hch⟩, hnr⟩ := hc
  have hs := Q.s_le_of_prec hp
  unfold running at hnr
  push Not at hnr
  refine ⟨hnr hs, ?_, hch⟩
  by_contra hge
  push Not at hge
  exact hch (hD.2 c j hge)

end Sched

/-- Proposition "Late charges", first part, the work bound:
`In_i < B_max + kL + k(L + δ)`. -/
theorem late_In (P : Sched I) (ch : J → J → Prop) (δ : ℝ) (hδ : 0 ≤ δ)
    (hD : P.DelayedCharges ch δ) (b : J → J → ℝ) (Bmax : ℝ) (hcap : P.RespectsCap b Bmax)
    (hG : P.IsGuardWith ch b) (i : J) (h : ∃ c, i < c ∧ P.prec c i) :
    P.In i < Bmax + I.k * I.L + I.k * (I.L + δ) := by
  obtain ⟨j, hij, hji, hlast⟩ := P.last_overtaker i h
  have hw := P.waitingAt_of_overtaker hij hji
  have h1 := P.In_split ch hlast
  have h2 := P.guardProp_of hG i j hw hij
  have h3 := (hcap i j hw).2
  have h4 := P.unch_run_le ch i j
  have h5 := P.sum_by_server_le _ (I.L + δ) (fun m =>
    P.stale_server_le m (P.s j) δ hδ _ (fun c hc => by
      rw [Finset.mem_filter] at hc
      have := P.unch_stale ch δ hD i j c hc.1
      exact ⟨hc.2, this.1, this.2.1⟩))
  rw [P.unch_split ch i j] at h1
  have h6 := I.hC_le j
  nlinarith

/-- Proposition "Late charges", inequality (eq:late). -/
theorem late_bound (P F : Sched I) (hF : IsFCFS F) (ch : J → J → Prop) (δ : ℝ)
    (hδ : 0 ≤ δ) (hD : P.DelayedCharges ch δ) (b : J → J → ℝ) (Bmax : ℝ) (hB : 0 ≤ Bmax)
    (hcap : P.RespectsCap b Bmax) (hG : P.IsGuardWith ch b) (i : J) :
    P.W i < F.W i + Bmax / I.k + (4 - 2 / (I.k : ℝ)) * I.L + δ := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hX : 0 < Bmax + I.k * I.L + I.k * (I.L + δ) := by nlinarith [I.hL]
  have := excess_lt_of_In P F hF i _ hX (late_In P ch δ hδ hD b Bmax hcap hG i)
  unfold excess at this
  have e : (Bmax + I.k * I.L + I.k * (I.L + δ)) / I.k = Bmax / I.k + 2 * I.L + δ := by
    field_simp; ring
  rw [e] at this
  nlinarith

/-- Per-server views (06:501-503): `excess < B_max/k + (3-2/k)L + (1-1/k)(L+δ)`. -/
theorem perServer_bound (P F : Sched I) (hF : IsFCFS F) (ch : J → J → Prop) (δ : ℝ)
    (hδ : 0 ≤ δ) (hD : P.PerServerCharges ch δ) (b : J → J → ℝ) (Bmax : ℝ) (hB : 0 ≤ Bmax)
    (hcap : P.RespectsCap b Bmax) (hG : P.IsGuardWith ch b) (i : J) :
    P.W i < F.W i + Bmax / I.k + (3 - 2 / (I.k : ℝ)) * I.L
      + (1 - 1 / (I.k : ℝ)) * (I.L + δ) := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hk1 : (0 : ℝ) ≤ (I.k : ℝ) - 1 := by
    have : (1 : ℝ) ≤ I.k := by exact_mod_cast I.hk
    linarith
  set X := Bmax + I.k * I.L + ((I.k : ℝ) - 1) * (I.L + δ) with hXd
  have hX : 0 < X := by
    have : 0 ≤ ((I.k : ℝ) - 1) * (I.L + δ) := mul_nonneg hk1 (by linarith [I.hL])
    nlinarith [I.hL]
  have hIn : (∃ c, i < c ∧ P.prec c i) → P.In i < X := by
    intro h
    obtain ⟨j, hij, hji, hlast⟩ := P.last_overtaker i h
    have hw := P.waitingAt_of_overtaker hij hji
    have h1 := P.In_split ch hlast
    have h2 := P.guardProp_of hG i j hw hij
    have h3 := (hcap i j hw).2
    have h4 := P.unch_run_le ch i j
    have h5 := P.sum_by_server_le_erase _ (I.L + δ) (P.srv j)
      (fun c hc => by
        have := P.unch_stale ch δ hD.1 i j c hc
        exact fun hs => this.2.2 (hD.2 c j hs this.1))
      (fun m => P.stale_server_le m (P.s j) δ hδ _ (fun c hc => by
        rw [Finset.mem_filter] at hc
        have := P.unch_stale ch δ hD.1 i j c hc.1
        exact ⟨hc.2, this.1, this.2.1⟩))
    rw [P.unch_split ch i j] at h1
    have h6 := I.hC_le j
    nlinarith
  have := excess_lt_of_In P F hF i X hX hIn
  unfold excess at this
  have e : X / I.k = Bmax / I.k + I.L + (1 - 1 / (I.k : ℝ)) * (I.L + δ) := by
    rw [hXd]; field_simp
  rw [e] at this
  linarith

namespace Sched

variable (Q : Sched I)

/-- Under report-before-pull, an uncharged overtaker started before `j` either is in
service at `s j` or finished exactly at `s j`. -/
lemma rbp_unch (ch : J → J → Prop) (hR : Q.ReportBeforePull ch) {i j : J}
    (hji : Q.prec j i) (c : J) (hic : i < c) (hcj : Q.prec c j) (hch : ¬ ch c j) :
    Q.running c (Q.s j) ∨ Q.s c + I.C c = Q.s j := by
  have hs := Q.s_le_of_prec hcj
  by_cases hr : Q.running c (Q.s j)
  · exact Or.inl hr
  right
  unfold running at hr
  push Not at hr
  have hf := hr hs
  rcases lt_or_eq_of_le hf with hlt | heq
  · exfalso
    set f := Q.s c + I.C c
    have hCc := I.hC_pos c
    have hai : I.a i ≤ Q.s c := (I.ha_mono hic.le).trans (Q.start_ge c)
    have hwait : ∃ q, I.a q ≤ f ∧ f < Q.s q :=
      ⟨i, by linarith, lt_of_lt_of_le hlt (Q.s_le_of_prec hji)⟩
    obtain ⟨j', hsrv, hs1, hs2⟩ := Q.work_conserving f hwait (Q.srv c)
    have hne : j' ≠ c := by
      intro e; subst e; linarith
    have hsj' : Q.s j' = f := by
      rcases Q.no_overlap j' c hne hsrv with h | h
      · linarith
      · linarith
    have hch' : ch c j' := hR.2.2 c j' (Ne.symm hne) hsrv.symm (by rw [hsj'])
    have hord : Q.ord j' < Q.ord j := Q.ord_refines j j' (by rw [hsj']; exact hlt)
    exact hch (hR.2.1 c j' j hch' hord)
  · exact heq

end Sched

/-- Proposition "Late charges", report-before-pull: inequality (eq:guardin) holds unchanged
for every delay, lost reports included. -/
theorem rbp_In (P : Sched I) (ch : J → J → Prop) (hR : P.ReportBeforePull ch)
    (b : J → J → ℝ) (Bmax : ℝ) (hcap : P.RespectsCap b Bmax) (hG : P.IsGuardWith ch b)
    (i : J) (h : ∃ c, i < c ∧ P.prec c i) : P.In i < Bmax + I.k * I.L := by
  obtain ⟨j, hij, hji, hlast⟩ := P.last_overtaker i h
  have hw := P.waitingAt_of_overtaker hij hji
  have h1 := P.In_split ch hlast
  have h2 := P.guardProp_of hG i j hw hij
  have h3 := (hcap i j hw).2
  set T := univ.filter (fun c => i < c ∧ P.prec c j ∧ ¬ ch c j) with hT
  have hmem : ∀ c ∈ T, i < c ∧ P.prec c j ∧ ¬ ch c j := fun c hc => by
    rw [hT, Finset.mem_filter] at hc; exact hc.2
  have hCj := I.hC_pos j
  -- every member of `T` is on a server other than `srv j`
  have hsrv : ∀ c ∈ T, P.srv c ≠ P.srv j := by
    intro c hc hs
    obtain ⟨hic, hcj, hch⟩ := hmem c hc
    have hne : c ≠ j := fun e => by rw [e] at hcj; exact P.prec_irrefl j hcj
    rcases P.rbp_unch ch hR hji c hic hcj hch with hr | hf
    · unfold Sched.running at hr
      rcases P.no_overlap c j hne hs with h' | h' <;> linarith [hr.1, hr.2]
    · exact hch (hR.2.2 c j hne hs (le_of_eq hf))
  -- and on pairwise distinct servers
  have hinj : Set.InjOn P.srv (T : Set J) := by
    intro c1 hc1 c2 hc2 hs
    by_contra hne
    obtain ⟨hic1, hcj1, hch1⟩ := hmem c1 hc1
    obtain ⟨hic2, hcj2, hch2⟩ := hmem c2 hc2
    have hC1 := I.hC_pos c1
    have hC2 := I.hC_pos c2
    have key : ∀ x y, x ∈ T → y ∈ T → x ≠ y → P.srv x = P.srv y →
        P.running x (P.s j) → P.s y + I.C y = P.s j → False := by
      intro x y hx hy hxy hsxy hrx hfy
      obtain ⟨_, hxj, _⟩ := hmem x hx
      obtain ⟨_, _, hchy⟩ := hmem y hy
      unfold Sched.running at hrx
      have hCy := I.hC_pos y
      rcases P.no_overlap x y hxy hsxy with h' | h'
      · linarith [P.s_le_of_prec (hmem y hy).2.1]
      · have hsx : P.s x = P.s j := by linarith
        have hchyx : ch y x := hR.2.2 y x (Ne.symm hxy) hsxy.symm (by linarith)
        exact hchy (hR.2.1 y x j hchyx hxj)
    rcases P.rbp_unch ch hR hji c1 hic1 hcj1 hch1 with hr1 | hf1 <;>
      rcases P.rbp_unch ch hR hji c2 hic2 hcj2 hch2 with hr2 | hf2
    · exact hne (P.srv_injOn_running (P.s j) hr1 hr2 hs)
    · exact key c1 c2 hc1 hc2 hne hs hr1 hf2
    · exact key c2 c1 hc2 hc1 (Ne.symm hne) hs.symm hr2 hf1
    · rcases P.no_overlap c1 c2 hne hs with h' | h' <;> linarith
  have hcard : T.card ≤ I.k - 1 := by
    have h1' : (univ.erase (P.srv j)).card = I.k - 1 := by
      simp [Finset.card_erase_of_mem]
    rw [← h1']
    apply Finset.card_le_card_of_injOn P.srv
    · intro c hc
      simp [hsrv c hc]
    · exact hinj
  have hc' : (T.card : ℝ) ≤ (I.k : ℝ) - 1 := by
    have : ((T.card : ℕ) : ℝ) ≤ ((I.k - 1 : ℕ) : ℝ) := by exact_mod_cast hcard
    rwa [Nat.cast_sub (Nat.succ_le_of_lt I.hk), Nat.cast_one] at this
  have h4 : ∑ c ∈ T, I.C c ≤ ((I.k : ℝ) - 1) * I.L :=
    calc ∑ c ∈ T, I.C c ≤ ∑ _c ∈ T, I.L := sum_le_sum fun c _ => I.hC_le c
      _ = (T.card : ℝ) * I.L := by simp
      _ ≤ ((I.k : ℝ) - 1) * I.L := mul_le_mul_of_nonneg_right hc' I.hL.le
  have h6 := I.hC_le j
  nlinarith

/-- Proposition "Late charges", report-before-pull: Theorem "Guard bound" holds unchanged. -/
theorem rbp_bound (P F : Sched I) (hF : IsFCFS F) (ch : J → J → Prop)
    (hR : P.ReportBeforePull ch) (b : J → J → ℝ) (Bmax : ℝ) (hB : 0 ≤ Bmax)
    (hcap : P.RespectsCap b Bmax) (hG : P.IsGuardWith ch b) (i : J) :
    P.W i < F.W i + Bmax / I.k + (3 - 2 / (I.k : ℝ)) * I.L :=
  guard_excess_of_In P F hF Bmax hB i (rbp_In P ch hR b Bmax hcap hG i)

/-! ## Proposition "Absolute bound" (06_theory.tex:425) -/

/-- `V` satisfies the recursion of 06:418-420: `V_1^- = 0` and
`V_i^- = max(0, V_{i-1}^- + C_{i-1} - k(a_i - a_{i-1}))`, where `i-1` is the job of the
next lower rank. -/
def IsFluid (I : Input J) (V : J → ℝ) : Prop :=
  (∀ i, (∀ l, ¬ l < i) → V i = 0) ∧
  (∀ i p, p < i → (∀ l, l < i → l ≤ p) → V i = max 0 (V p + I.C p - I.k * (I.a i - I.a p)))

/-- The job of the next lower rank. -/
def predOf (i : J) (h : ∃ l, l < i) : J :=
  (univ.filter (· < i)).max' (by obtain ⟨l, hl⟩ := h; exact ⟨l, by simp [hl]⟩)

lemma predOf_lt (i : J) (h : ∃ l, l < i) : predOf i h < i := by
  have := Finset.max'_mem (univ.filter (· < i))
    (by obtain ⟨l, hl⟩ := h; exact ⟨l, by simp [hl]⟩)
  rw [Finset.mem_filter] at this
  exact this.2

lemma le_predOf (i : J) (h : ∃ l, l < i) {l : J} (hl : l < i) : l ≤ predOf i h :=
  Finset.le_max' _ _ (by simp [hl])

/-- The solution of the recursion. -/
def fluidV (I : Input J) : J → ℝ :=
  (wellFounded_lt (α := J)).fix fun i rec =>
    if h : ∃ l, l < i then
      max 0 (rec (predOf i h) (predOf_lt i h) + I.C (predOf i h)
        - I.k * (I.a i - I.a (predOf i h)))
    else 0

/-- The recursion has a solution, so the hypotheses `IsFluid I V` below are not vacuous. -/
lemma fluidV_isFluid : IsFluid I (fluidV I) := by
  constructor
  · intro i hi
    unfold fluidV
    rw [WellFounded.fix_eq, dif_neg (fun ⟨l, hl⟩ => hi l hl)]
  · intro i p hp hmax
    have h : ∃ l, l < i := ⟨p, hp⟩
    have hpe : predOf i h = p :=
      le_antisymm (hmax _ (predOf_lt i h)) (le_predOf i h hp)
    conv_lhs => unfold fluidV; rw [WellFounded.fix_eq, dif_pos h]
    change max 0 (fluidV I (predOf i h) + I.C (predOf i h)
      - I.k * (I.a i - I.a (predOf i h))) = _
    rw [hpe]

lemma IsFluid.nonneg {V : J → ℝ} (hV : IsFluid I V) (i : J) : 0 ≤ V i := by
  by_cases h : ∃ l, l < i
  · rw [hV.2 i (predOf i h) (predOf_lt i h) (fun l hl => le_predOf i h hl)]
    exact le_max_left _ _
  · rw [hV.1 i (fun l hl => h ⟨l, hl⟩)]

namespace Sched

variable (Q : Sched I)

lemma rem_antitone (j : J) {u v : ℝ} (huv : u ≤ v) : Q.rem j v ≤ Q.rem j u := by
  have := Q.rem_sub_rem (j := j) huv
  linarith [Q.exec_nonneg j u v]

/-- A set `S` of jobs that have all arrived by `u`, while the other jobs start at or after
`v`: on `[u, v]` its remaining work either drops to `(k-1)b` or drains at rate `k`. -/
lemma drain (S : Finset J) {u v : ℝ} (huv : u ≤ v) (b : ℝ) (hb0 : 0 ≤ b)
    (hCb : ∀ j, I.C j ≤ b) (hin : ∀ j ∈ S, I.a j ≤ u) (hout : ∀ j, j ∉ S → v ≤ Q.s j) :
    ∑ j ∈ S, Q.rem j v ≤ max (((I.k : ℝ) - 1) * b) (∑ j ∈ S, Q.rem j u - I.k * (v - u)) := by
  by_cases hex : ∃ t ∈ Icc u v, ∑ j ∈ S, Q.rem j t ≤ ((I.k : ℝ) - 1) * b
  · obtain ⟨t, ht, hle⟩ := hex
    have : ∑ j ∈ S, Q.rem j v ≤ ∑ j ∈ S, Q.rem j t :=
      sum_le_sum fun j _ => Q.rem_antitone j ht.2
    exact le_max_of_le_left (this.trans hle)
  · push Not at hex
    have hbusy : ∀ t ∈ Ioo u v, ∀ m, ∃ j, Q.srv j = m ∧ Q.running j t := by
      intro t ht m
      by_contra hidle
      have hlt := hex t ⟨ht.1.le, ht.2.le⟩
      have hnw : ∀ j ∈ S, Q.s j ≤ t := by
        intro j hj
        by_contra h
        push Not at h
        exact hidle (Q.work_conserving t ⟨j, (hin j hj).trans ht.1.le, h⟩ m)
      have : ∑ j ∈ S, Q.rem j t ≤ ((I.k : ℝ) - 1) * b := by
        rw [← Finset.sum_filter_of_ne (p := fun j => Q.running j t)]
        · apply Q.sum_rem_le_b t m _ b hb0
          · intro j hj
            rw [Finset.mem_filter] at hj
            exact ⟨hj.2, fun h => hidle ⟨j, h, hj.2⟩⟩
          · intro j _
            exact (Q.rem_le_C j t).trans (hCb j)
        · intro j hj hne
          by_contra hr
          exact hne (Q.rem_eq_zero_of_not_running (hnw j hj) hr)
      linarith
    have hge := Q.sum_exec_ge huv hbusy
    have hall : ∑ j, (Q.rem j u - Q.rem j v) = ∑ j ∈ S, (Q.rem j u - Q.rem j v) := by
      rw [← Finset.sum_subset (Finset.subset_univ S)]
      intro j _ hj
      rw [Q.rem_of_le_s (huv.trans (hout j hj)), Q.rem_of_le_s (hout j hj), sub_self]
    have := Q.sum_rem_sub huv
    rw [hall, Finset.sum_sub_distrib] at this
    exact le_max_of_le_right (by linarith)

/-- Lemma "Fluid comparison" (S4.11) read at arrivals, with any bound `b` on the costs:
`R^Q_i ≤ V_i^- + (k-1)b`. -/
theorem R_le_fluid (V : J → ℝ) (hV : IsFluid I V) (b : ℝ) (hb0 : 0 ≤ b)
    (hCb : ∀ j, I.C j ≤ b) (i : J) : Q.R i ≤ V i + ((I.k : ℝ) - 1) * b := by
  have hk1 : (0 : ℝ) ≤ ((I.k : ℝ) - 1) * b := by
    have : (1 : ℝ) ≤ I.k := by exact_mod_cast I.hk
    exact mul_nonneg (by linarith) hb0
  induction i using WellFoundedLT.induction with
  | _ i ih =>
  by_cases h : ∃ l, l < i
  · set p := predOf i h
    have hp : p < i := predOf_lt i h
    have hmax : ∀ l, l < i → l ≤ p := fun l hl => le_predOf i h hl
    have hS : univ.filter (· < i) = insert p (univ.filter (· < p)) := by
      ext l
      simp only [Finset.mem_filter, Finset.mem_univ, true_and, Finset.mem_insert]
      constructor
      · intro hl
        rcases lt_or_eq_of_le (hmax l hl) with h' | h'
        · exact Or.inr h'
        · exact Or.inl h'
      · rintro (rfl | h')
        · exact hp
        · exact h'.trans hp
    have hd := Q.drain (univ.filter (· < i)) (I.ha_mono hp.le) b hb0 hCb
      (fun j hj => by
        rw [Finset.mem_filter] at hj
        exact I.ha_mono (hmax j hj.2))
      (fun j hj => by
        simp only [Finset.mem_filter, Finset.mem_univ, true_and, not_lt] at hj
        exact (I.ha_mono hj).trans (Q.start_ge j))
    have hRp : ∑ j ∈ univ.filter (· < i), Q.rem j (I.a p) = Q.R p + I.C p := by
      rw [hS, Finset.sum_insert (by simp), Q.rem_of_le_s (Q.start_ge p)]
      unfold R
      ring
    rw [hRp] at hd
    have hIH := ih p hp
    have hVi := hV.2 i p hp hmax
    unfold R
    refine hd.trans (max_le ?_ ?_)
    · linarith [hV.nonneg i]
    · rw [hVi]
      have := le_max_right 0 (V p + I.C p - I.k * (I.a i - I.a p))
      linarith
  · have : Q.R i = 0 := by
      apply sum_eq_zero
      intro j hj
      rw [Finset.mem_filter] at hj
      exact absurd ⟨j, hj.2⟩ h
    rw [this, hV.1 i (fun l hl => h ⟨l, hl⟩)]
    linarith

/-- Proposition "Absolute bound", the general inequality with any cost bound `b`. -/
theorem absolute_le_b (V : J → ℝ) (hV : IsFluid I V) (b : ℝ) (hb0 : 0 ≤ b)
    (hCb : ∀ j, I.C j ≤ b) (i : J) :
    (I.k : ℝ) * Q.W i ≤ V i + ((I.k : ℝ) - 1) * b + Q.In i := by
  have h1 := Q.busy i
  have h2 := Out_nonneg Q i
  have h3 := Q.beta_nonneg i
  have h4 := Q.R_le_fluid V hV b hb0 hCb i
  linarith

end Sched

/-- Proposition "Absolute bound": `k W[i] ≤ V_i^- + (k-1)L + In_i` for every
non-preemptive work-conserving policy. -/
theorem absolute_le (Q : Sched I) (V : J → ℝ) (hV : IsFluid I V) (i : J) :
    (I.k : ℝ) * Q.W i ≤ V i + ((I.k : ℝ) - 1) * I.L + Q.In i :=
  Q.absolute_le_b V hV I.L I.hL.le I.hC_le i

/-- Proposition "Absolute bound", FCFS: `W_FCFS[i] ≤ (V_i^- + (k-1)L)/k`. -/
theorem absolute_fcfs (F : Sched I) (hF : IsFCFS F) (V : J → ℝ) (hV : IsFluid I V) (i : J) :
    F.W i ≤ (V i + ((I.k : ℝ) - 1) * I.L) / I.k := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have := absolute_le F V hV i
  rw [fcfs_In hF, add_zero] at this
  rw [le_div_iff₀ hk]
  linarith

lemma absolute_of_In (Q : Sched I) (V : J → ℝ) (hV : IsFluid I V) (Y : ℝ) (hY : 0 ≤ Y)
    (i : J) (h : (∃ c, i < c ∧ Q.prec c i) → Q.In i < Y + I.k * I.L) :
    Q.W i < (V i + Y) / I.k + (2 - 1 / (I.k : ℝ)) * I.L := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hIn : Q.In i < Y + I.k * I.L := by
    by_cases hc : ∃ c, i < c ∧ Q.prec c i
    · exact h hc
    · rw [Q.In_eq_zero i hc]; nlinarith [I.hL]
  have := absolute_le Q V hV i
  have e : (V i + Y) / I.k + (2 - 1 / (I.k : ℝ)) * I.L
      = (V i + Y + (2 * (I.k : ℝ) - 1) * I.L) / I.k := by field_simp
  rw [e, lt_div_iff₀ hk]
  linarith

/-- Proposition "Absolute bound", inequality (eq:absolute) under the guard. -/
theorem absolute_guard (P : Sched I) (b : J → J → ℝ) (Bmax : ℝ) (hB : 0 ≤ Bmax)
    (hcap : P.RespectsCap b Bmax) (hG : P.IsGuard b) (V : J → ℝ) (hV : IsFluid I V)
    (σ : ℝ) (hσ : ∀ j, V j + I.C j ≤ σ) (i : J) :
    P.W i < (V i + Bmax) / I.k + (2 - 1 / (I.k : ℝ)) * I.L ∧
    (V i + Bmax) / I.k + (2 - 1 / (I.k : ℝ)) * I.L
      ≤ (σ + Bmax) / I.k + (2 - 1 / (I.k : ℝ)) * I.L := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  refine ⟨absolute_of_In P V hV Bmax hB i (guard_In P b Bmax hcap hG i), ?_⟩
  have : V i ≤ σ := by linarith [hσ i, I.hC_pos i]
  have : (V i + Bmax) / I.k ≤ (σ + Bmax) / I.k := div_le_div_of_nonneg_right (by linarith) hk.le
  linarith

/-- The clock obeys the absolute bound with `kθ` in place of `B_max` (06:451-452). -/
theorem absolute_timeout (P : Sched I) (θ : ℝ) (hθ : 0 ≤ θ) (hT : P.IsTimeout θ)
    (V : J → ℝ) (hV : IsFluid I V) (i : J) :
    P.W i < (V i + I.k * θ) / I.k + (2 - 1 / (I.k : ℝ)) * I.L := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  refine absolute_of_In P V hV _ (mul_nonneg hk.le hθ) i (fun h => ?_)
  have := timeout_In P θ hT i h
  linarith

/-- The deadline rule of 06:447-450: `B_max = kD - σ - (2k-1)L ≥ 0` gives `W < D`. -/
theorem deadline (P : Sched I) (b : J → J → ℝ) (D σ : ℝ) (V : J → ℝ) (hV : IsFluid I V)
    (hσ : ∀ j, V j + I.C j ≤ σ)
    (hB : 0 ≤ (I.k : ℝ) * D - σ - (2 * (I.k : ℝ) - 1) * I.L)
    (hcap : P.RespectsCap b ((I.k : ℝ) * D - σ - (2 * (I.k : ℝ) - 1) * I.L))
    (hG : P.IsGuard b) (i : J) : P.W i < D := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have h := absolute_guard P b _ hB hcap hG V hV σ hσ i
  have e : (σ + ((I.k : ℝ) * D - σ - (2 * (I.k : ℝ) - 1) * I.L)) / I.k
      + (2 - 1 / (I.k : ℝ)) * I.L = D := by field_simp; ring
  linarith [h.1, h.2]

/-! ## Corollary "Largest flow time" (06_theory.tex:324) -/

/-- A schedule of the input on `k` servers "with or without interruption" (06:321-322),
relaxed to fractional rates: job `j` runs at rate `x j t ∈ [0, 1]`, the rates add up to at
most `k`, `j` runs only after its arrival and not after `f j`, and it receives its cost.
Every preemptive schedule, with or without migration, is one of these, so `Fstar` below is
at most the paper's `F^*` and the corollary stated with it is at least as strong. -/
structure PSched (I : Input J) where
  x : J → ℝ → ℝ
  f : J → ℝ
  integrable : ∀ j, Integrable (x j)
  nonneg : ∀ j t, 0 ≤ x j t
  le_one : ∀ j t, x j t ≤ 1
  cap : ∀ t, ∑ j, x j t ≤ I.k
  before : ∀ j t, t < I.a j → x j t = 0
  after : ∀ j t, f j < t → x j t = 0
  total : ∀ j, ∫ t, x j t = I.C j

/-- Some schedule has largest flow time at most `F`. -/
def Achieves (I : Input J) (F : ℝ) : Prop := ∃ p : PSched I, ∀ j, p.f j - I.a j ≤ F

/-- `F^*`: the smallest achievable largest flow time. -/
def Fstar (I : Input J) : ℝ := sInf {F | Achieves I F}

namespace PSched

variable (p : PSched I)

lemma setInt_eq (j : J) {u w : ℝ} (hu : u ≤ I.a j) (hw : p.f j ≤ w) :
    ∫ t in Icc u w, p.x j t = I.C j := by
  rw [setIntegral_eq_integral_of_forall_compl_eq_zero, p.total]
  intro t ht
  rw [Set.mem_Icc, not_and_or, not_le, not_le] at ht
  rcases ht with h | h
  · exact p.before j t (by linarith)
  · exact p.after j t (by linarith)

/-- A job runs at rate at most `1`, so its flow time is at least its cost. -/
lemma C_le_flow (j : J) : I.C j ≤ p.f j - I.a j := by
  have h1 := p.setInt_eq j (le_refl (I.a j)) (le_refl (p.f j))
  have h2 : ∫ t in Icc (I.a j) (p.f j), p.x j t ≤ ∫ t in Icc (I.a j) (p.f j), (1 : ℝ) :=
    setIntegral_mono_on (p.integrable j).integrableOn
      (integrableOn_const measure_Icc_lt_top.ne) measurableSet_Icc
      (fun t _ => p.le_one j t)
  rw [setIntegral_const, Real.volume_real_Icc, smul_eq_mul, mul_one] at h2
  have hC := I.hC_pos j
  rcases le_or_gt (I.a j) (p.f j) with h | h
  · rw [max_eq_left (by linarith)] at h2; linarith
  · rw [max_eq_right (by linarith)] at h2; linarith

/-- Work that arrives in `[u, w']` and must finish by `w` fits into `k (w - u)`. -/
lemma window (u w : ℝ) (huw : u ≤ w) (T : Finset J)
    (hT : ∀ j ∈ T, u ≤ I.a j ∧ p.f j ≤ w) :
    ∑ j ∈ T, I.C j ≤ (I.k : ℝ) * (w - u) := by
  have e : ∑ j ∈ T, I.C j = ∫ t in Icc u w, ∑ j ∈ T, p.x j t := by
    rw [integral_finset_sum T (fun j _ => (p.integrable j).integrableOn)]
    exact sum_congr rfl fun j hj => (p.setInt_eq j (hT j hj).1 (hT j hj).2).symm
  have h2 : ∫ t in Icc u w, ∑ j ∈ T, p.x j t ≤ ∫ t in Icc u w, (I.k : ℝ) :=
    setIntegral_mono_on
      (integrable_finset_sum T (fun j _ => (p.integrable j))).integrableOn
      (integrableOn_const measure_Icc_lt_top.ne) measurableSet_Icc
      (fun t _ => (Finset.sum_le_sum_of_subset_of_nonneg (Finset.subset_univ T)
        (fun j _ _ => p.nonneg j t)).trans (p.cap t))
  rw [setIntegral_const, Real.volume_real_Icc, smul_eq_mul, max_eq_left (by linarith)] at h2
  linarith

end PSched

/-- The run of a non-preemptive schedule is a schedule in the sense of `PSched`. -/
def Sched.toPSched (Q : Sched I) : PSched I where
  x j := (Ico (Q.s j) (Q.s j + I.C j)).indicator (fun _ => (1 : ℝ))
  f j := Q.s j + I.C j
  integrable j := (integrableOn_const measure_Ico_lt_top.ne).integrable_indicator
    measurableSet_Ico
  nonneg j t := Set.indicator_nonneg (fun _ _ => zero_le_one) t
  le_one j t := by
    unfold Set.indicator; split_ifs <;> norm_num
  cap t := by
    have e : ∑ j, (Ico (Q.s j) (Q.s j + I.C j)).indicator (fun _ => (1 : ℝ)) t
        = ((univ.filter (fun j => Q.running j t)).card : ℝ) := by
      rw [Finset.card_eq_sum_ones, Nat.cast_sum, Finset.sum_filter]
      apply sum_congr rfl
      intro j _
      unfold Set.indicator Sched.running
      simp [Set.mem_Ico]
    rw [e]
    have : (univ.filter (fun j => Q.running j t)).card ≤ (univ : Finset (Fin I.k)).card := by
      apply Finset.card_le_card_of_injOn Q.srv
      · intro j _; simp
      · intro j1 hj1 j2 hj2 h
        simp only [Finset.coe_filter, Finset.mem_univ, true_and, Set.mem_setOf_eq] at hj1 hj2
        exact Q.srv_injOn_running t hj1 hj2 h
    rw [Finset.card_univ, Fintype.card_fin] at this
    exact_mod_cast this
  before j t h := Set.indicator_of_notMem (fun hm => by
    rw [Set.mem_Ico] at hm; linarith [Q.start_ge j, hm.1]) _
  after j t h := Set.indicator_of_notMem (fun hm => by
    rw [Set.mem_Ico] at hm; linarith [hm.2]) _
  total j := by
    rw [integral_indicator_const _ measurableSet_Ico, smul_eq_mul, mul_one, vol_job]

lemma achieves_nonempty (Q : Sched I) : {F | Achieves I F}.Nonempty := by
  refine ⟨∑ j, (Q.s j + I.C j - I.a j), Q.toPSched, fun j => ?_⟩
  show Q.s j + I.C j - I.a j ≤ _
  exact Finset.single_le_sum (f := fun j => Q.s j + I.C j - I.a j)
    (fun j _ => by linarith [Q.start_ge j, I.hC_pos j]) (Finset.mem_univ j)

/-- `V_i^- + C_i` is at most `X` when every window of ranks `[j, i]` carries at most
`k (a_i - a_j) + X` of work. -/
lemma fluid_le_window {V : J → ℝ} (hV : IsFluid I V) (i : J) :
    ∀ X : ℝ, (∀ j, j ≤ i →
      ∑ l ∈ univ.filter (fun l => j ≤ l ∧ l ≤ i), I.C l ≤ I.k * (I.a i - I.a j) + X) →
      V i + I.C i ≤ X := by
  induction i using WellFoundedLT.induction with
  | _ i ih =>
  intro X hX
  have hCi : I.C i ≤ X := by
    have := hX i le_rfl
    have e : univ.filter (fun l => i ≤ l ∧ l ≤ i) = {i} := by
      ext l; simp [le_antisymm_iff, and_comm]
    rw [e, Finset.sum_singleton] at this
    linarith
  by_cases h : ∃ l, l < i
  · set p := predOf i h
    have hp : p < i := predOf_lt i h
    have hmax : ∀ l, l < i → l ≤ p := fun l hl => le_predOf i h hl
    rw [hV.2 i p hp hmax]
    have hIH := ih p hp (X - I.C i + I.k * (I.a i - I.a p)) (by
      intro j hj
      have h1 := hX j (hj.trans hp.le)
      have e : univ.filter (fun l => j ≤ l ∧ l ≤ i)
          = insert i (univ.filter (fun l => j ≤ l ∧ l ≤ p)) := by
        ext l
        simp only [Finset.mem_filter, Finset.mem_univ, true_and, Finset.mem_insert]
        constructor
        · rintro ⟨h1, h2⟩
          rcases lt_or_eq_of_le h2 with h3 | h3
          · exact Or.inr ⟨h1, hmax l h3⟩
          · exact Or.inl h3
        · rintro (rfl | ⟨h1, h2⟩)
          · exact ⟨hj.trans hp.le, le_rfl⟩
          · exact ⟨h1, h2.trans hp.le⟩
      rw [e, Finset.sum_insert (by simp [not_le.mpr hp])] at h1
      linarith)
    rcases le_total 0 (V p + I.C p - I.k * (I.a i - I.a p)) with h0 | h0
    · rw [max_eq_right h0]; linarith
    · rw [max_eq_left h0]; linarith
  · rw [hV.1 i (fun l hl => h ⟨l, hl⟩)]; linarith

/-- FCFS is within `(3 - 2/k)` of any achievable largest flow time:
`W_FCFS[i] + C_i ≤ (3 - 2/k) F`. -/
theorem fcfs_flow (F : Sched I) (hF : IsFCFS F) (Fv : ℝ) (hA : Achieves I Fv) (i : J) :
    F.W i + I.C i ≤ (3 - 2 / (I.k : ℝ)) * Fv := by
  obtain ⟨p, hp⟩ := hA
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hk1 : (1 : ℝ) ≤ I.k := by exact_mod_cast I.hk
  have hCF : ∀ j, I.C j ≤ Fv := fun j => (p.C_le_flow j).trans (hp j)
  have hF0 : 0 ≤ Fv := (I.hC_pos i).le.trans (hCF i)
  have h1 := F.absolute_le_b (fluidV I) fluidV_isFluid Fv hF0 hCF i
  rw [fcfs_In hF, add_zero] at h1
  have h2 := fluid_le_window (fluidV_isFluid (I := I)) i (I.k * Fv) (by
    intro j hj
    have := p.window (I.a j) (I.a i + Fv) (by linarith [I.ha_mono hj])
      (univ.filter (fun l => j ≤ l ∧ l ≤ i)) (by
        intro l hl
        rw [Finset.mem_filter] at hl
        refine ⟨I.ha_mono hl.2.1, ?_⟩
        linarith [hp l, I.ha_mono hl.2.2])
    linarith)
  have hCi := hCF i
  -- k (W + C) ≤ (2k - 1) F + (k - 1) C ≤ (3k - 2) F
  have h3 : (I.k : ℝ) * (F.W i + I.C i) ≤ (3 * (I.k : ℝ) - 2) * Fv := by
    have : ((I.k : ℝ) - 1) * I.C i ≤ ((I.k : ℝ) - 1) * Fv :=
      mul_le_mul_of_nonneg_left hCi (by linarith)
    nlinarith
  have e : (3 - 2 / (I.k : ℝ)) * Fv = (3 * (I.k : ℝ) - 2) * Fv / I.k := by field_simp
  rw [e, le_div_iff₀ hk]
  linarith

/-- At `k = 1` the factor is `1`: FCFS attains `F^*` on one server (06:343-344). -/
theorem fcfs_flow_k1 (hk1 : I.k = 1) (F : Sched I) (hF : IsFCFS F) (i : J) :
    F.W i + I.C i ≤ Fstar I := by
  apply le_csInf (achieves_nonempty F)
  intro Fv hFv
  have := fcfs_flow F hF Fv hFv i
  rw [hk1, Nat.cast_one] at this
  linarith

/-- Corollary "Largest flow time": under the cap of Corollary "The cap for a given bound",
`W_P[i] + C_i < (3 - 2/k) F^* + G`. -/
theorem maxflow (P F : Sched I) (hF : IsFCFS F) (b : J → J → ℝ) (G : ℝ)
    (hG3 : (3 - 2 / (I.k : ℝ)) * I.L ≤ G)
    (hcap : P.RespectsCap b (I.k * (G - (3 - 2 / (I.k : ℝ)) * I.L))) (hG : P.IsGuard b)
    (i : J) : P.W i + I.C i < (3 - 2 / (I.k : ℝ)) * Fstar I + G := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hk1 : (1 : ℝ) ≤ I.k := by exact_mod_cast I.hk
  have hc : 0 < 3 - 2 / (I.k : ℝ) := by
    have : 2 / (I.k : ℝ) ≤ 2 := by rw [div_le_iff₀ hk]; linarith
    linarith
  have hex := cap_for_bound P F hF b G hG3 hcap hG i
  unfold excess at hex
  have hfl : (F.W i + I.C i) / (3 - 2 / (I.k : ℝ)) ≤ Fstar I := by
    apply le_csInf (achieves_nonempty F)
    intro Fv hFv
    rw [div_le_iff₀ hc]
    linarith [fcfs_flow F hF Fv hFv i]
  rw [div_le_iff₀ hc] at hfl
  linarith

/-! ## Theorem "Price of the guarantee" (06_theory.tex:564) -/

/-- Counting inverted pairs twice (S8.5): `Σ Out_i - Σ In_i = Σ_{u<v, v ≺ u} (C_u - C_v)`. -/
lemma sum_Out_sub_In (Q : Sched I) :
    ∑ i, Q.Out i - ∑ i, Q.In i
      = ∑ u, ∑ v, (if u < v ∧ Q.prec v u then I.C u - I.C v else 0) := by
  have hO : ∑ i, Q.Out i = ∑ u, ∑ v, (if u < v ∧ Q.prec v u then I.C u else 0) := by
    unfold Sched.Out
    simp only [Finset.sum_filter]
    exact Finset.sum_comm
  have hI : ∑ i, Q.In i = ∑ u, ∑ v, (if u < v ∧ Q.prec v u then I.C v else 0) := by
    unfold Sched.In
    simp only [Finset.sum_filter]
  rw [hO, hI, ← Finset.sum_sub_distrib]
  apply sum_congr rfl
  intro u _
  rw [← Finset.sum_sub_distrib]
  apply sum_congr rfl
  intro v _
  split_ifs <;> ring

/-- Summing Theorem "Net-overtake identity" over all jobs:
`k Σ (W_FCFS - W_Q) = (Σ Out - Σ In) - Σ Δ` with `|Σ Δ| ≤ |J| · 2(k-1)L`. -/
lemma sum_saving (Q F : Sched I) (hF : IsFCFS F) :
    ∃ E, |E| ≤ (Fintype.card J : ℝ) * (2 * ((I.k : ℝ) - 1) * I.L) ∧
      (I.k : ℝ) * (∑ i, F.W i - ∑ i, Q.W i) = (∑ i, Q.Out i - ∑ i, Q.In i) - E := by
  refine ⟨∑ i, Delta Q F i, ?_, ?_⟩
  · calc |∑ i, Delta Q F i| ≤ ∑ i, |Delta Q F i| := Finset.abs_sum_le_sum_abs _ _
      _ ≤ ∑ _i : J, 2 * ((I.k : ℝ) - 1) * I.L :=
          sum_le_sum fun i _ => identity_bound Q F hF i
      _ = _ := by simp
  · unfold Delta
    rw [← Finset.sum_sub_distrib, ← Finset.sum_sub_distrib, Finset.mul_sum,
      Finset.sum_sub_distrib, Finset.sum_sub_distrib, Finset.sum_sub_distrib]
    simp only [mul_sub, Finset.sum_sub_distrib, ← Finset.mul_sum]
    ring

/-- Theorem "Price of the guarantee". `m` jobs of cost `L` and `n` jobs of cost `c < L`,
all arriving at `0`, the long ones ranked first; `P` keeps `excess ≤ G` for every job; `S`
is SJF on this input (a strictly shorter job is always started first). -/
theorem price (P F S : Sched I) (hF : IsFCFS F) (m n : ℕ) (c G : ℝ)
    (hc0 : 0 < c) (hcL : c < I.L)
    (ha : ∀ j, I.a j = 0) (hcost : ∀ j, I.C j = I.L ∨ I.C j = c)
    (hrank : ∀ u v, I.C u = I.L → I.C v = c → u < v)
    (hm : (univ.filter (fun j => I.C j = I.L)).card = m)
    (hn : (univ.filter (fun j => I.C j = c)).card = n)
    (hSJF : ∀ u v, I.C v < I.C u → S.prec v u)
    (hG : ∀ j, excess P F j ≤ G)
    (hD : (m : ℝ) * n * (I.L - c) / I.k > 2 * (1 - 1 / (I.k : ℝ)) * I.L * (m + n)) :
    let Wbar := fun Q : Sched I => (∑ j, Q.W j) / ((m : ℝ) + n)
    let D0 := (m : ℝ) * n * (I.L - c) / I.k
    let H := 2 * (1 - 1 / (I.k : ℝ)) * I.L * (m + n)
    let α := ((I.k : ℝ) * G + (3 * (I.k : ℝ) - 2) * I.L) / (n * c)
    (Wbar F - Wbar P) / (Wbar F - Wbar S) ≤ α + H * (1 + α) / (D0 - H) := by
  intro Wbar D0 H α
  have _ := ha
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hk1 : (1 : ℝ) ≤ I.k := by exact_mod_cast I.hk
  have hL := I.hL
  have hLc : I.L ≠ c := ne_of_gt hcL
  -- the number of jobs
  have hcard : (Fintype.card J : ℝ) = m + n := by
    have h := Finset.card_filter_add_card_filter_not (s := (univ : Finset J))
      (fun j => I.C j = I.L)
    have e : univ.filter (fun j => ¬ I.C j = I.L) = univ.filter (fun j => I.C j = c) := by
      ext j
      simp only [Finset.mem_filter, Finset.mem_univ, true_and]
      rcases hcost j with h' | h'
      · simp [h', hLc]
      · simp [h', hLc.symm]
    rw [e, hm, hn, Finset.card_univ] at h
    rw [← h]; push_cast; ring
  set B := (I.k : ℝ) * G + (3 * (I.k : ℝ) - 2) * I.L with hB
  have hD0H : H < D0 := hD
  have hH0 : 0 ≤ H := by
    have : 0 ≤ 1 - 1 / (I.k : ℝ) := by
      have : 1 / (I.k : ℝ) ≤ 1 := by rw [div_le_iff₀ hk]; linarith
      linarith
    positivity
  have hmn : (0 : ℝ) < (m : ℝ) * n := by
    have : 0 < (m : ℝ) * n * (I.L - c) / I.k := lt_of_le_of_lt hH0 hD0H
    have h2 : 0 < (m : ℝ) * n * (I.L - c) := by
      have := mul_pos this hk
      rwa [div_mul_cancel₀ _ hk.ne'] at this
    by_contra hneg
    push Not at hneg
    nlinarith [mul_le_mul_of_nonneg_right hneg (show (0:ℝ) ≤ I.L - c by linarith)]
  have hm0 : (0 : ℝ) < m := by
    rcases Nat.eq_zero_or_pos m with h | h
    · rw [h] at hmn; simp at hmn
    · exact_mod_cast h
  have hn0 : (0 : ℝ) < n := by
    rcases Nat.eq_zero_or_pos n with h | h
    · rw [h] at hmn; simp at hmn
    · exact_mod_cast h
  -- B ≥ 0, from Corollary "A work budget is necessary" at a long job
  have hB0 : 0 ≤ B := by
    have : (univ.filter (fun j => I.C j = I.L)).Nonempty := by
      rw [← Finset.card_pos, hm]; exact_mod_cast hm0
    obtain ⟨u, _⟩ := this
    have := necessary P F hF G hG u
    linarith [P.In_nonneg u]
  -- numerator
  have hnum : ∑ i, P.Out i - ∑ i, P.In i ≤ (m : ℝ) * ((I.L - c) / c * B) := by
    rw [sum_Out_sub_In]
    have hstep : ∀ u, ∑ v, (if u < v ∧ P.prec v u then I.C u - I.C v else 0)
        ≤ if I.C u = I.L then (I.L - c) / c * B else 0 := by
      intro u
      rcases hcost u with hu | hu
      · rw [if_pos hu]
        have h1 : ∑ v, (if u < v ∧ P.prec v u then I.C u - I.C v else 0)
            ≤ ∑ v, (if u < v ∧ P.prec v u then (I.L - c) / c * I.C v else 0) := by
          apply sum_le_sum
          intro v _
          split_ifs
          · rw [hu]
            rcases hcost v with hv | hv
            · rw [hv, sub_self]; positivity
            · rw [hv]; field_simp; try linarith
          · exact le_refl _
        have h2 : ∑ v, (if u < v ∧ P.prec v u then (I.L - c) / c * I.C v else 0)
            = (I.L - c) / c * P.In u := by
          unfold Sched.In
          rw [Finset.mul_sum, Finset.sum_filter]
        have h3 := necessary P F hF G hG u
        have h4 : (I.L - c) / c * P.In u ≤ (I.L - c) / c * B :=
          mul_le_mul_of_nonneg_left h3 (div_nonneg (by linarith) hc0.le)
        linarith
      · rw [if_neg (by rw [hu]; exact hLc.symm)]
        apply sum_nonpos
        intro v _
        split_ifs
        · rw [hu]; rcases hcost v with hv | hv <;> rw [hv] <;> linarith
        · exact le_refl _
    calc _ ≤ ∑ u, (if I.C u = I.L then (I.L - c) / c * B else 0) := sum_le_sum fun u _ => hstep u
      _ = (m : ℝ) * ((I.L - c) / c * B) := by
        rw [← Finset.sum_filter, Finset.sum_const, hm, nsmul_eq_mul]
  -- denominator
  have hden : ∑ i, S.Out i - ∑ i, S.In i = (m : ℝ) * n * (I.L - c) := by
    rw [sum_Out_sub_In]
    have hrow : ∀ u, ∑ v, (if u < v ∧ S.prec v u then I.C u - I.C v else 0)
        = if I.C u = I.L then (n : ℝ) * (I.L - c) else 0 := by
      intro u
      have hcell : ∀ v, (if u < v ∧ S.prec v u then I.C u - I.C v else 0)
          = if I.C u = I.L ∧ I.C v = c then I.L - c else 0 := by
        intro v
        rcases hcost u with hu | hu <;> rcases hcost v with hv | hv
        · simp [hu, hv, hLc]
        · rw [if_pos ⟨hrank u v hu hv, hSJF u v (by rw [hu, hv]; exact hcL)⟩,
            if_pos ⟨hu, hv⟩, hu, hv]
        · have : ¬ u < v := not_lt.mpr (hrank v u hv hu).le
          simp [this, hu, hv, hLc.symm]
        · simp [hu, hv, hLc.symm]
      simp only [hcell]
      split_ifs with hu
      · simp only [hu, true_and]
        rw [← Finset.sum_filter, Finset.sum_const, hn, nsmul_eq_mul]
      · simp [hu]
    simp only [hrow]
    rw [← Finset.sum_filter, Finset.sum_const, hm, nsmul_eq_mul]
    ring
  -- the two savings
  obtain ⟨EP, hEP, hSP⟩ := sum_saving P F hF
  obtain ⟨ES, hES, hSS⟩ := sum_saving S F hF
  rw [hcard] at hEP hES
  have hkH : ((m : ℝ) + n) * (2 * ((I.k : ℝ) - 1) * I.L) = I.k * H := by
    simp only [H]; field_simp
  rw [hkH] at hEP hES
  have hEP' := (abs_le.mp hEP)
  have hES' := (abs_le.mp hES)
  set SP := ∑ i, F.W i - ∑ i, P.W i
  set SS := ∑ i, F.W i - ∑ i, S.W i
  set N := (m : ℝ) * ((I.L - c) / c * B) / I.k
  have hSPle : SP ≤ N + H := by
    have : (I.k : ℝ) * SP ≤ (I.k : ℝ) * (N + H) := by
      have e : (I.k : ℝ) * (N + H) = (m : ℝ) * ((I.L - c) / c * B) + I.k * H := by
        simp only [N]; field_simp
      rw [e]; linarith
    exact le_of_mul_le_mul_left this hk
  have hSSge : D0 - H ≤ SS := by
    have : (I.k : ℝ) * (D0 - H) ≤ (I.k : ℝ) * SS := by
      have e : (I.k : ℝ) * (D0 - H) = (m : ℝ) * n * (I.L - c) - I.k * H := by
        simp only [D0]; field_simp
      rw [e, hSS, hden]; linarith
    exact le_of_mul_le_mul_left this hk
  have hpos : 0 < D0 - H := by linarith
  have hN0 : 0 ≤ N := by
    simp only [N]
    have : 0 ≤ (I.L - c) / c * B := mul_nonneg (div_nonneg (by linarith) hc0.le) hB0
    positivity
  have hmn' : (0 : ℝ) < (m : ℝ) + n := by linarith
  have eW : (Wbar F - Wbar P) / (Wbar F - Wbar S) = SP / SS := by
    simp only [Wbar, SP, SS]
    rw [← sub_div, ← sub_div, div_div_div_cancel_right₀ hmn'.ne']
  rw [eW]
  have hSS0 : 0 < SS := lt_of_lt_of_le hpos hSSge
  have h1 : SP / SS ≤ (N + H) / SS := div_le_div_of_nonneg_right hSPle hSS0.le
  have h2 : (N + H) / SS ≤ (N + H) / (D0 - H) :=
    div_le_div_of_nonneg_left (by linarith) hpos hSSge
  have h3 : (N + H) / (D0 - H) = α + H * (1 + α) / (D0 - H) := by
    have hNα : N = D0 * α := by
      simp only [N, D0, α, B]
      field_simp
    rw [hNα]
    field_simp
    ring
  linarith

/-! ## Proposition "Floor" (06_theory.tex:539) -/

/-- The input of the floor (S4.8): `k + 1` jobs of cost `L`, all arriving at `0`. -/
def floorInput (k : ℕ) (hk : 0 < k) (L : ℝ) (hL : 0 < L) : Input (Fin (k + 1)) where
  k := k
  L := L
  a := fun _ => 0
  C := fun _ => L
  hk := hk
  hL := hL
  ha_nonneg := fun _ => le_refl 0
  ha_mono := fun _ _ _ => le_refl 0
  hC_pos := fun _ => hL
  hC_le := fun _ => le_refl L

section Floor

variable {k : ℕ} {hk : 0 < k} {L : ℝ} {hL : 0 < L}

@[simp] lemma floorInput_a (j : Fin (k + 1)) : (floorInput k hk L hL).a j = 0 := rfl
@[simp] lemma floorInput_C (j : Fin (k + 1)) : (floorInput k hk L hL).C j = L := rfl
@[simp] lemma floorInput_k : (floorInput k hk L hL).k = k := rfl
@[simp] lemma floorInput_L : (floorInput k hk L hL).L = L := rfl

/-- The core of the floor: whatever happens after the first decision, if the first job
started is the last-ranked one, some job has excess at least `L`. -/
theorem floor_core (P F : Sched (floorInput k hk L hL)) (hF : IsFCFS F)
    (hfirst : ∀ j, P.ord (Fin.last k) ≤ P.ord j) :
    ∃ i, L ≤ excess P F i := by
  -- some job starts at `L` or later under `P`
  have hA : ∃ j, L ≤ P.s j := by
    by_contra hcon
    push Not at hcon
    have hinj : Set.InjOn P.srv (univ : Finset (Fin (k + 1))) := by
      intro i _ j _ hs
      by_contra hne
      have hi := P.start_ge i
      have hj := P.start_ge j
      simp only [floorInput_a, floorInput_C] at hi hj
      rcases P.no_overlap i j hne hs with h | h <;>
        simp only [floorInput_C] at h <;> linarith [hcon i, hcon j]
    have := Finset.card_le_card_of_injOn P.srv (fun j _ => Finset.mem_univ (P.srv j)) hinj
    have c1 : (univ : Finset (Fin (k + 1))).card = k + 1 := Finset.card_fin _
    have c2 : (univ : Finset (Fin (floorInput k hk L hL).k)).card = k := Finset.card_fin _
    rw [c1, c2] at this
    omega
  -- some job other than the last starts at `L` or later
  have hB : ∃ i, i ≠ Fin.last k ∧ L ≤ P.s i := by
    obtain ⟨j, hj⟩ := hA
    by_cases hjl : j = Fin.last k
    · refine ⟨⟨0, by omega⟩, fun h => ?_, ?_⟩
      · have := congrArg Fin.val h
        simp at this
        omega
      · by_contra hlt
        push Not at hlt
        have := P.ord_refines (Fin.last k) ⟨0, by omega⟩ (by rw [← hjl]; linarith)
        exact absurd (hfirst ⟨0, by omega⟩) (not_le.mpr this)
    · exact ⟨j, hjl, hj⟩
  obtain ⟨i, hil, hi⟩ := hB
  -- FCFS starts every job but the last at `0`
  have hFi : F.s i = 0 := by
    have h0 := F.start_ge i
    simp only [floorInput_a] at h0
    by_contra hne
    have hpos : 0 < F.s i := lt_of_le_of_ne h0 (Ne.symm hne)
    have hwait : ∃ i', (floorInput k hk L hL).a i' ≤ 0 ∧ 0 < F.s i' := ⟨i, by simp, hpos⟩
    choose g hg using F.work_conserving 0 hwait
    have hglt : ∀ m, g m < i := fun m => by
      have hs0 : F.s (g m) = 0 := by
        have := F.start_ge (g m)
        simp only [floorInput_a] at this
        linarith [(hg m).2.1]
      exact (hF i (g m)).1 (F.ord_refines i (g m) (by rw [hs0]; exact hpos))
    have hginj : Function.Injective g := by
      intro m1 m2 h
      rw [← (hg m1).1, ← (hg m2).1, h]
    have hival : i.val < k := by
      have : i.val ≠ k := fun h => hil (Fin.ext (by simp [h]))
      omega
    have hcard := Finset.card_le_card_of_injOn (fun m => (g m).val)
      (s := (univ : Finset (Fin k))) (t := range i.val)
      (fun m _ => by
        rw [Finset.mem_coe, Finset.mem_range]; exact Fin.lt_iff_val_lt_val.mp (hglt m))
      (fun m1 _ m2 _ h => hginj (Fin.ext h))
    simp at hcard
    omega
  refine ⟨i, ?_⟩
  unfold excess Sched.W
  simp only [floorInput_a]
  linarith

/-- A schedule of the floor input from a dispatch position `pos`: positions `0, ..., k-1`
start at `0` on servers `0, ..., k-1`, and position `k` starts at `L` on server `0`. -/
def mkSched (pos : Fin (k + 1) → ℕ) (hinj : Function.Injective pos) (hle : ∀ j, pos j ≤ k)
    (hsurj : ∀ m, m ≤ k → ∃ j, pos j = m) : Sched (floorInput k hk L hL) where
  s j := if pos j < k then 0 else L
  srv j := ⟨pos j % k, Nat.mod_lt _ hk⟩
  ord := pos
  start_ge j := by
    simp only [floorInput_a]
    split_ifs <;> linarith
  ord_inj := hinj
  ord_refines i j h := by
    have h' : (if pos j < k then (0:ℝ) else L) < (if pos i < k then 0 else L) := h
    show pos j < pos i
    split_ifs at h' with h1 h2 <;> first | (exfalso; linarith) | omega
  no_overlap i j hij hs := by
    simp only [floorInput_C]
    have hm : pos i % k = pos j % k := by
      have := congrArg Fin.val hs
      simpa using this
    have hne : pos i ≠ pos j := fun h => hij (hinj h)
    have hi := hle i
    have hj := hle j
    split_ifs with h1 h2 h2
    · rw [Nat.mod_eq_of_lt h1, Nat.mod_eq_of_lt h2] at hm; exact absurd hm hne
    · left; linarith
    · right; linarith
    · exfalso; omega
  work_conserving t hw m := by
    obtain ⟨i, hi1, hi2⟩ := hw
    simp only [floorInput_a] at hi1
    have hmk : m.val < k := m.isLt
    have hi2' : t < (if pos i < k then (0:ℝ) else L) := hi2
    have hiL : t < L := by
      split_ifs at hi2' <;> linarith
    obtain ⟨j, hj⟩ := hsurj m.val (by omega)
    refine ⟨j, Fin.ext ?_, ?_, ?_⟩
    · show pos j % k = m.val
      rw [hj, Nat.mod_eq_of_lt hmk]
    · show (if pos j < k then (0:ℝ) else L) ≤ t
      rw [if_pos (by rw [hj]; exact hmk)]
      exact hi1
    · show t < (if pos j < k then (0:ℝ) else L) + (floorInput k hk L hL).C j
      rw [if_pos (by rw [hj]; exact hmk), floorInput_C]
      linarith

/-- The FCFS run of the floor input. -/
def floorFCFS : Sched (floorInput k hk L hL) :=
  mkSched (hk := hk) (hL := hL) (fun j => j.val) Fin.val_injective (fun j => Fin.is_le j)
    (fun m hm => ⟨⟨m, by omega⟩, rfl⟩)

lemma floorFCFS_isFCFS : IsFCFS (floorFCFS (k := k) (hk := hk) (L := L) (hL := hL)) :=
  fun _ _ => Fin.lt_iff_val_lt_val.symm

/-- Greedy choice: at each step the earliest member of the eligible part of the remaining
set if it is non-empty, otherwise any remaining member. -/
lemma greedy (W0 : Finset (Fin (k + 1))) (E : ℕ → Fin (k + 1) → Prop) (r : ℕ)
    (hr : r ≤ W0.card) :
    ∃ f : ℕ → Fin (k + 1), ∀ t < r, f t ∈ W0 ∧ f t ∉ (range t).image f ∧
      ((∃ q ∈ W0, q ∉ (range t).image f ∧ E t q) →
        E t (f t) ∧ ∀ q ∈ W0, q ∉ (range t).image f → E t q → f t ≤ q) := by
  induction r with
  | zero => exact ⟨fun _ => 0, fun t ht => absurd ht (Nat.not_lt_zero t)⟩
  | succ r ih =>
    obtain ⟨f, hf⟩ := ih (by omega)
    set R := W0 \ (range r).image f
    have hR : R.Nonempty := by
      have : ((range r).image f).card < W0.card := by
        have := Finset.card_image_le (s := range r) (f := f)
        rw [Finset.card_range] at this
        omega
      obtain ⟨x, hx, hnx⟩ := Finset.exists_mem_notMem_of_card_lt_card this
      exact ⟨x, Finset.mem_sdiff.mpr ⟨hx, hnx⟩⟩
    set ER := R.filter (E r)
    let pick : Fin (k + 1) := if h : ER.Nonempty then ER.min' h else R.min' hR
    have himg : ∀ t ≤ r, (range t).image (Function.update f r pick) = (range t).image f := by
      intro t ht
      apply Finset.image_congr
      intro x hx
      simp only [Finset.coe_range, Set.mem_Iio] at hx
      exact Function.update_of_ne (by omega) _ _
    refine ⟨Function.update f r pick, fun t ht => ?_⟩
    rcases Nat.lt_succ_iff_lt_or_eq.mp ht with ht | ht
    · rw [himg t ht.le, Function.update_of_ne (by omega)]
      exact hf t ht
    · subst ht
      rw [himg t le_rfl, Function.update_self]
      have hpR : pick ∈ R := by
        simp only [pick]
        split_ifs with h
        · exact (Finset.mem_filter.mp (ER.min'_mem h)).1
        · exact R.min'_mem hR
      rw [Finset.mem_sdiff] at hpR
      refine ⟨hpR.1, hpR.2, fun ⟨q, hq, hqn, hEq⟩ => ?_⟩
      have hne : ER.Nonempty := ⟨q, by simp [ER, R, hq, hqn, hEq]⟩
      simp only [pick, dif_pos hne]
      refine ⟨(Finset.mem_filter.mp (ER.min'_mem hne)).2, fun q' hq' hqn' hE' => ?_⟩
      exact ER.min'_le q' (by simp [ER, R, hq', hqn', hE'])

/-- Proposition "Floor": for every budget rule that gives every waiting job a positive
budget at the first dispatch decision there are a run of Algorithm guard and a job with
excess at least `L`.  The rule `ρ q n` is the budget of `q` at the `n`-th decision (from
`0`); it may depend on the job and the decision.  In the run, the base policy starts the
last-ranked job at the first decision and the earliest-arrived waiting job otherwise, so
it reads no cost. -/
theorem floor (ρ : Fin (k + 1) → ℕ → ℝ) (hρ : ∀ q, 0 < ρ q 0) :
    ∃ P : Sched (floorInput k hk L hL),
      P.IsGuard (fun q j => ρ q (P.ord j)) ∧ P.ord (Fin.last k) = 0 ∧
      ∃ i, L ≤ excess P (floorFCFS (hk := hk) (hL := hL)) i := by
  set last := Fin.last k
  set W0 := (univ : Finset (Fin (k + 1))).erase last with hW0
  have hW0card : W0.card = k := by simp [W0]
  obtain ⟨f, hf⟩ := greedy W0 (fun t q => ρ q (t + 1) ≤ 0) (k - 1) (by omega)
  -- the jobs chosen at positions 1 .. k-1 are distinct
  have hfinj : ∀ t1 t2, t1 < k - 1 → t2 < k - 1 → f t1 = f t2 → t1 = t2 := by
    intro t1 t2 h1 h2 he
    by_contra hne
    rcases lt_or_gt_of_ne hne with h | h
    · exact (hf t2 h2).2.1 (Finset.mem_image.mpr ⟨t1, Finset.mem_range.mpr h, he⟩)
    · exact (hf t1 h1).2.1 (Finset.mem_image.mpr ⟨t2, Finset.mem_range.mpr h, he.symm⟩)
  set img := (range (k - 1)).image f
  have himgsub : img ⊆ W0 := by
    intro x hx
    obtain ⟨t, ht, rfl⟩ := Finset.mem_image.mp hx
    exact (hf t (Finset.mem_range.mp ht)).1
  have himgcard : img.card = k - 1 := by
    rw [Finset.card_image_of_injOn (fun t1 h1 t2 h2 he => hfinj t1 t2
      (Finset.mem_range.mp h1) (Finset.mem_range.mp h2) he), Finset.card_range]
  have hrest : (W0 \ img).card = 1 := by
    rw [Finset.card_sdiff_of_subset himgsub, hW0card, himgcard]; omega
  obtain ⟨w, hw⟩ := Finset.card_eq_one.mp hrest
  have hwW : w ∈ W0 \ img := by rw [hw]; exact Finset.mem_singleton_self w
  rw [Finset.mem_sdiff] at hwW
  -- every job is `last`, some `f t`, or `w`
  have hcls : ∀ j, j = last ∨ (∃ t, t < k - 1 ∧ f t = j) ∨ j = w := by
    intro j
    by_cases hj : j = last
    · exact Or.inl hj
    by_cases hj2 : ∃ t, t < k - 1 ∧ f t = j
    · exact Or.inr (Or.inl hj2)
    right; right
    have : j ∈ W0 \ img := by
      rw [Finset.mem_sdiff]
      refine ⟨by simp [W0, hj], fun hm => ?_⟩
      obtain ⟨t, ht, he⟩ := Finset.mem_image.mp hm
      exact hj2 ⟨t, Finset.mem_range.mp ht, he⟩
    rw [hw] at this
    exact Finset.mem_singleton.mp this
  have hfl : ∀ t, t < k - 1 → f t ≠ last := fun t ht h => by
    have := (hf t ht).1
    rw [h] at this
    simp [W0] at this
  have hwl : w ≠ last := fun h => by
    have := hwW.1
    rw [h] at this
    simp [W0] at this
  have hwf : ¬ ∃ t, t < k - 1 ∧ f t = w := fun ⟨t, ht, he⟩ =>
    hwW.2 (Finset.mem_image.mpr ⟨t, Finset.mem_range.mpr ht, he⟩)
  -- positions
  let pos : Fin (k + 1) → ℕ := fun j =>
    if j = last then 0 else if h : ∃ t, t < k - 1 ∧ f t = j then Nat.find h + 1 else k
  have hpos_last : pos last = 0 := by simp [pos]
  have hpos_f : ∀ t, t < k - 1 → pos (f t) = t + 1 := by
    intro t ht
    have hex : ∃ t', t' < k - 1 ∧ f t' = f t := ⟨t, ht, rfl⟩
    simp only [pos, if_neg (hfl t ht), dif_pos hex]
    have hs := Nat.find_spec hex
    have := hfinj _ _ hs.1 ht hs.2
    omega
  have hpos_w : pos w = k := by simp [pos, hwl, hwf]
  have hle : ∀ j, pos j ≤ k := by
    intro j
    rcases hcls j with rfl | ⟨t, ht, rfl⟩ | rfl
    · rw [hpos_last]; omega
    · rw [hpos_f t ht]; omega
    · rw [hpos_w]
  have hinj : Function.Injective pos := by
    intro j1 j2 he
    rcases hcls j1 with h1 | ⟨t1, ht1, h1⟩ | h1 <;>
      rcases hcls j2 with h2 | ⟨t2, ht2, h2⟩ | h2
    · rw [h1, h2]
    · subst h1 h2; rw [hpos_last, hpos_f t2 ht2] at he; omega
    · subst h1 h2; rw [hpos_last, hpos_w] at he; omega
    · subst h1 h2; rw [hpos_f t1 ht1, hpos_last] at he; omega
    · subst h1 h2; rw [hpos_f t1 ht1, hpos_f t2 ht2] at he
      have : t1 = t2 := by omega
      rw [this]
    · subst h1 h2; rw [hpos_f t1 ht1, hpos_w] at he; omega
    · subst h1 h2; rw [hpos_w, hpos_last] at he; omega
    · subst h1 h2; rw [hpos_w, hpos_f t2 ht2] at he; omega
    · rw [h1, h2]
  have hsurj : ∀ m, m ≤ k → ∃ j, pos j = m := by
    intro m hm
    rcases Nat.eq_zero_or_pos m with h0 | h0
    · exact ⟨last, by rw [hpos_last, h0]⟩
    · rcases lt_or_eq_of_le hm with h1 | h1
      · exact ⟨f (m - 1), by rw [hpos_f _ (by omega)]; omega⟩
      · exact ⟨w, by rw [hpos_w, h1]⟩
  set P := mkSched (hk := hk) (hL := hL) pos hinj hle hsurj with hP
  have hPs : ∀ j, P.s j = if pos j < k then 0 else L := fun j => rfl
  have hPord : ∀ j, P.ord j = pos j := fun j => rfl
  have hwaitP : ∀ q j, P.waitingAt q j ↔ (q = j ∨ pos j < pos q) := by
    intro q j
    unfold Sched.waitingAt Sched.prec
    rw [hPord, hPord]
    constructor
    · exact fun h => h.2
    · intro h
      refine ⟨?_, h⟩
      simp only [floorInput_a, hPs]
      split_ifs <;> linarith
  have hover0 : ∀ q j, pos j < k → overC (floorInput k hk L hL) P.doneBy q j = 0 := by
    intro q j hj
    apply sum_eq_zero
    intro c hc
    rw [Finset.mem_filter] at hc
    exfalso
    have h1 := hc.2.2
    unfold Sched.doneBy at h1
    rw [hPs, hPs, if_pos hj, floorInput_C] at h1
    split_ifs at h1 <;> linarith
  refine ⟨P, ?_, hpos_last, ?_⟩
  · intro j hex
    rcases hcls j with hj | ⟨t, ht, hj⟩ | hj <;> subst j
    · -- the first decision: nobody is eligible
      exfalso
      obtain ⟨q, _, hq⟩ := hex
      dsimp only at hq
      rw [hover0 q last (by rw [hpos_last]; exact hk), hPord, hpos_last] at hq
      linarith [hρ q]
    · -- a decision at time `0` after the first
      have hW : ∀ q, P.waitingAt q (f t) ↔ (q ∈ W0 ∧ q ∉ (range t).image f) := by
        intro q
        rw [hwaitP, hpos_f t ht]
        constructor
        · rintro (rfl | h)
          · exact ⟨(hf t ht).1, (hf t ht).2.1⟩
          · refine ⟨?_, fun hm => ?_⟩
            · rw [hW0, Finset.mem_erase]
              refine ⟨fun hq => ?_, Finset.mem_univ q⟩
              rw [hq, hpos_last] at h; omega
            · obtain ⟨t', ht', rfl⟩ := Finset.mem_image.mp hm
              rw [Finset.mem_range] at ht'
              rw [hpos_f t' (by omega)] at h; omega
        · rintro ⟨hq, hqn⟩
          rcases hcls q with rfl | ⟨t', ht', rfl⟩ | rfl
          · simp [W0] at hq
          · rcases lt_trichotomy t' t with h | h | h
            · exact absurd (Finset.mem_image.mpr ⟨t', Finset.mem_range.mpr h, rfl⟩) hqn
            · left; rw [h]
            · right; rw [hpos_f t' ht']; omega
          · right; rw [hpos_w]; omega
      have hE : ∀ q, P.elig P.doneBy (fun q j => ρ q (P.ord j)) q (f t) ↔
          ((q ∈ W0 ∧ q ∉ (range t).image f) ∧ ρ q (t + 1) ≤ 0) := by
        intro q
        unfold Sched.elig
        dsimp only
        rw [hW, hover0 q (f t) (by rw [hpos_f t ht]; omega), hPord, hpos_f t ht]
      obtain ⟨q, hq⟩ := hex
      rw [hE] at hq
      obtain ⟨h1, h2⟩ := (hf t ht).2.2 ⟨q, hq.1.1, hq.1.2, hq.2⟩
      refine ⟨(hE _).mpr ⟨⟨(hf t ht).1, (hf t ht).2.1⟩, h1⟩, fun q' hq' => ?_⟩
      rw [hE] at hq'
      exact h2 q' hq'.1.1 hq'.1.2 hq'.2
    · -- the decision at time `L`: only `w` waits
      have hW : ∀ q, P.waitingAt q w → q = w := by
        intro q hq
        rw [hwaitP, hpos_w] at hq
        rcases hq with h | h
        · exact h
        · exact absurd (hle q) (by omega)
      obtain ⟨q, hq⟩ := hex
      have := hW q hq.1
      subst this
      exact ⟨hq, fun q' hq' => le_of_eq (hW q' hq'.1).symm⟩
  · exact floor_core P floorFCFS floorFCFS_isFCFS (fun j => by rw [hPord, hpos_last]; omega)

end Floor

#print axioms guard_In
#print axioms guard_bound
#print axioms guard_bound_dup
#print axioms cap_for_bound
#print axioms cap_pos_iff
#print axioms guard_fcfs_of_zero
#print axioms guard_cap_zero_fcfs
#print axioms budgetFamily_respects
#print axioms guard_mult
#print axioms timeout_In
#print axioms timeout_bound
#print axioms combined_bounds
#print axioms combined_clock_any_reports
#print axioms absolute_le
#print axioms absolute_fcfs
#print axioms absolute_guard
#print axioms absolute_timeout
#print axioms deadline
#print axioms fluidV_isFluid
#print axioms fcfs_flow
#print axioms maxflow
#print axioms fcfs_flow_k1
#print axioms late_In
#print axioms late_bound
#print axioms Sched.delayedCharges_of_d
#print axioms perServer_bound
#print axioms rbp_In
#print axioms rbp_bound
#print axioms price
#print axioms floor_core
#print axioms floor

end Overtake
